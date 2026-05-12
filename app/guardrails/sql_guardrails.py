from dataclasses import dataclass, field
from enum import Enum

import sqlparse
import sqlparse.sql as sql_nodes
import sqlparse.tokens as T
import structlog

log = structlog.get_logger(__name__)

_DDL_KEYWORDS = frozenset({"CREATE", "DROP", "ALTER", "TRUNCATE", "RENAME"})
_DML_WRITE_KEYWORDS = frozenset({"INSERT", "UPDATE", "DELETE", "MERGE", "UPSERT"})
_DANGEROUS_FUNCTIONS = frozenset(
    {"PG_READ_FILE", "PG_EXECUTE", "COPY", "EVAL", "DBLINK", "PG_CANCEL_BACKEND"}
)
_SYSTEM_SCHEMAS = frozenset({"PG_CATALOG", "INFORMATION_SCHEMA", "PG_TOAST"})
_MAX_SUBQUERY_DEPTH = 3


class ViolationType(str, Enum):
    DDL_STATEMENT = "DDL_STATEMENT"
    DML_WRITE = "DML_WRITE"
    UNBOUNDED_SCAN = "UNBOUNDED_SCAN"
    DEEP_SUBQUERY = "DEEP_SUBQUERY"
    SYSTEM_TABLE_ACCESS = "SYSTEM_TABLE_ACCESS"
    DANGEROUS_FUNCTION = "DANGEROUS_FUNCTION"
    MULTIPLE_STATEMENTS = "MULTIPLE_STATEMENTS"
    COMMENT_INJECTION = "COMMENT_INJECTION"


@dataclass
class GuardrailResult:
    passed: bool
    violations: list[ViolationType]
    violation_details: list[str]
    sanitised_sql: str | None
    blocked: bool


def check(sql: str) -> GuardrailResult:
    violations: list[ViolationType] = []
    details: list[str] = []
    blocked = False
    sanitised_sql = sql.strip()

    # --- Parse with sqlparse ---
    statements = sqlparse.parse(sanitised_sql)
    if not statements:
        violations.append(ViolationType.DDL_STATEMENT)
        details.append("Empty or unparseable SQL.")
        return GuardrailResult(passed=False, violations=violations, violation_details=details, sanitised_sql=None, blocked=True)

    # --- Multiple statements (injection vector) ---
    valid_stmts = [s for s in statements if s.get_type() is not None or str(s).strip()]
    real_stmts = [s for s in valid_stmts if str(s).strip()]
    if len(real_stmts) > 1:
        violations.append(ViolationType.MULTIPLE_STATEMENTS)
        details.append(
            f"Multiple statements detected ({len(real_stmts)}). Only one SELECT is permitted."
        )
        blocked = True

    # Use only the first statement for all further checks
    stmt = statements[0]

    # --- Comment injection ---
    if _has_comment_injection(sanitised_sql):
        violations.append(ViolationType.COMMENT_INJECTION)
        details.append("SQL comments detected (-- or /* */). Comments are not permitted.")
        blocked = True

    # --- DDL check ---
    if _is_ddl(stmt):
        violations.append(ViolationType.DDL_STATEMENT)
        details.append(
            f"DDL statement detected (keyword: {_get_first_keyword(stmt)}). "
            "Schema modifications are not permitted."
        )
        blocked = True

    # --- DML write check ---
    if _is_dml_write(stmt):
        violations.append(ViolationType.DML_WRITE)
        details.append(
            f"Write operation detected (keyword: {_get_first_keyword(stmt)}). "
            "Only SELECT queries are permitted."
        )
        blocked = True

    # --- System table access ---
    sys_tables = _find_system_table_access(stmt)
    if sys_tables:
        violations.append(ViolationType.SYSTEM_TABLE_ACCESS)
        details.append(
            f"System table access detected: {', '.join(sys_tables)}. "
            "Querying system catalogs is not permitted."
        )
        blocked = True

    # --- Dangerous functions ---
    dangerous = _find_dangerous_functions(stmt)
    if dangerous:
        violations.append(ViolationType.DANGEROUS_FUNCTION)
        details.append(
            f"Dangerous function(s) detected: {', '.join(dangerous)}. Not permitted."
        )
        blocked = True

    # --- Subquery depth (soft warning only) ---
    depth = _max_subquery_depth(stmt)
    if depth > _MAX_SUBQUERY_DEPTH:
        violations.append(ViolationType.DEEP_SUBQUERY)
        details.append(
            f"Subquery nesting depth {depth} exceeds limit of {_MAX_SUBQUERY_DEPTH}. "
            "Query allowed but flagged for review."
        )
        # Not blocked — soft warning

    # --- Unbounded scan (soft fix: inject LIMIT) ---
    if not blocked and not _has_limit(stmt):
        sanitised_sql = _inject_limit(sanitised_sql, 1000)
        violations.append(ViolationType.UNBOUNDED_SCAN)
        details.append("No LIMIT clause found. LIMIT 1000 injected automatically.")
        # Not blocked — auto-fixed

    passed = not blocked
    if blocked:
        sanitised_sql = None

    log.info(
        "guardrail_check",
        passed=passed,
        blocked=blocked,
        violations=[v.value for v in violations],
    )
    return GuardrailResult(
        passed=passed,
        violations=violations,
        violation_details=details,
        sanitised_sql=sanitised_sql,
        blocked=blocked,
    )


# ---------------------------------------------------------------------------
# Internal helpers — use sqlparse AST, never raw regex on keywords
# ---------------------------------------------------------------------------

def _get_first_keyword(stmt: sql_nodes.Statement) -> str:
    for token in stmt.tokens:
        if token.ttype in (T.Keyword.DDL, T.Keyword.DML, T.Keyword):
            return token.normalized.upper()
    return "UNKNOWN"


def _is_ddl(stmt: sql_nodes.Statement) -> bool:
    for token in stmt.flatten():
        if token.ttype is T.Keyword.DDL:
            if token.normalized.upper() in _DDL_KEYWORDS:
                return True
    return False


def _is_dml_write(stmt: sql_nodes.Statement) -> bool:
    for token in stmt.flatten():
        if token.ttype is T.Keyword.DML:
            if token.normalized.upper() in _DML_WRITE_KEYWORDS:
                return True
        # MERGE / UPSERT may appear as generic keywords in some sqlparse versions
        if token.ttype is T.Keyword:
            if token.normalized.upper() in {"MERGE", "UPSERT"}:
                return True
    return False


def _find_system_table_access(stmt: sql_nodes.Statement) -> list[str]:
    found: list[str] = []
    for token in stmt.flatten():
        if token.ttype in (T.Name, T.Literal.String.Single):
            upper = token.value.upper().strip('"\'`')
            if upper in _SYSTEM_SCHEMAS:
                found.append(token.value)
            # Also catch schema-qualified references like pg_catalog.pg_tables
            if "." in token.value:
                schema_part = token.value.split(".")[0].upper().strip('"\'`')
                if schema_part in _SYSTEM_SCHEMAS:
                    found.append(token.value)
    # Also scan for identifiers like pg_catalog.pg_tables written as a single token
    sql_upper = str(stmt).upper()
    for schema in _SYSTEM_SCHEMAS:
        if schema in sql_upper:
            if schema not in [f.upper() for f in found]:
                found.append(schema.lower())
    return list(set(found))


def _find_dangerous_functions(stmt: sql_nodes.Statement) -> list[str]:
    found: list[str] = []
    for token in stmt.flatten():
        if token.ttype in (T.Name, T.Keyword):
            if token.normalized.upper() in _DANGEROUS_FUNCTIONS:
                found.append(token.normalized.upper())
    # Also check raw text for COPY which can appear as a command
    sql_upper = str(stmt).upper()
    if sql_upper.strip().startswith("COPY"):
        found.append("COPY")
    return list(set(found))


def _has_limit(stmt: sql_nodes.Statement) -> bool:
    for token in stmt.flatten():
        if token.ttype is T.Keyword and token.normalized.upper() == "LIMIT":
            return True
    return False


def _inject_limit(sql: str, limit: int) -> str:
    stripped = sql.rstrip().rstrip(";")
    return f"{stripped} LIMIT {limit}"


def _has_comment_injection(sql: str) -> bool:
    # Check for inline comments (--) and block comments (/* */)
    # Use sqlparse token types rather than raw string search
    parsed = sqlparse.parse(sql)
    for stmt in parsed:
        for token in stmt.flatten():
            if token.ttype in (T.Comment.Single, T.Comment.Multiline):
                return True
    return False


def _max_subquery_depth(stmt: sql_nodes.Statement, current: int = 0) -> int:
    max_depth = current
    for token in stmt.tokens:
        if isinstance(token, sql_nodes.Parenthesis):
            # Check if it contains a SELECT (i.e., is a subquery)
            inner_tokens = list(token.flatten())
            is_subquery = any(
                t.ttype is T.Keyword.DML and t.normalized.upper() == "SELECT"
                for t in inner_tokens
            )
            if is_subquery:
                depth = _max_subquery_depth(token, current + 1)
                max_depth = max(max_depth, depth)
        elif hasattr(token, "tokens"):
            depth = _max_subquery_depth(token, current)
            max_depth = max(max_depth, depth)
    return max_depth
