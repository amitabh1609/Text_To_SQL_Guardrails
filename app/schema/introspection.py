from dataclasses import dataclass, field
from typing import Any

import structlog
from sqlalchemy import Engine, Inspector, inspect, text

log = structlog.get_logger(__name__)


@dataclass
class ColumnInfo:
    name: str
    data_type: str
    nullable: bool
    is_primary_key: bool = False
    foreign_key: str | None = None
    sample_values: list[str] = field(default_factory=list)


@dataclass
class TableSchema:
    table_name: str
    columns: list[ColumnInfo]
    row_count_estimate: int
    primary_keys: list[str]
    foreign_keys: dict[str, str]  # column_name → referenced table.column


def get_full_schema(engine: Engine) -> dict[str, TableSchema]:
    inspector: Inspector = inspect(engine)
    table_names = inspector.get_table_names()
    schemas: dict[str, TableSchema] = {}

    for table_name in table_names:
        pk_constraint = inspector.get_pk_constraint(table_name)
        pk_columns = set(pk_constraint.get("constrained_columns", []))

        fk_map: dict[str, str] = {}
        for fk in inspector.get_foreign_keys(table_name):
            for local_col, ref_col in zip(
                fk["constrained_columns"], fk["referred_columns"]
            ):
                fk_map[local_col] = f"{fk['referred_table']}.{ref_col}"

        raw_columns = inspector.get_columns(table_name)
        columns: list[ColumnInfo] = []
        for col in raw_columns:
            col_name = col["name"]
            sample_vals: list[str] = []
            if str(col["type"]).upper().startswith(("VARCHAR", "TEXT", "CHAR")):
                sample_vals = _get_sample_values(engine, table_name, col_name)
            columns.append(
                ColumnInfo(
                    name=col_name,
                    data_type=str(col["type"]),
                    nullable=col.get("nullable", True),
                    is_primary_key=col_name in pk_columns,
                    foreign_key=fk_map.get(col_name),
                    sample_values=sample_vals,
                )
            )

        row_count = _estimate_row_count(engine, table_name)
        schemas[table_name] = TableSchema(
            table_name=table_name,
            columns=columns,
            row_count_estimate=row_count,
            primary_keys=list(pk_columns),
            foreign_keys=fk_map,
        )
        log.debug("schema_reflected", table=table_name, columns=len(columns), rows=row_count)

    return schemas


def _get_sample_values(engine: Engine, table_name: str, column_name: str) -> list[str]:
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    f'SELECT DISTINCT "{column_name}" FROM "{table_name}" '
                    f'WHERE "{column_name}" IS NOT NULL LIMIT 5'
                )
            )
            return [str(row[0]) for row in result.fetchall()]
    except Exception:
        return []


def _estimate_row_count(engine: Engine, table_name: str) -> int:
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT reltuples::bigint AS estimate FROM pg_class "
                    "WHERE relname = :tname"
                ),
                {"tname": table_name},
            )
            row = result.fetchone()
            if row and row[0] > 0:
                return int(row[0])
            # Fall back to exact count for small tables
            result2 = conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"'))
            return int(result2.scalar() or 0)
    except Exception:
        return 0


def schema_to_prompt_text(schema: dict[str, TableSchema]) -> str:
    """Render filtered schema as a compact string for LLM prompts."""
    lines: list[str] = []
    for table_name, ts in schema.items():
        lines.append(f"\nTable: {table_name}  (~{ts.row_count_estimate:,} rows)")
        for col in ts.columns:
            flags: list[str] = []
            if col.is_primary_key:
                flags.append("PK")
            if col.foreign_key:
                flags.append(f"FK→{col.foreign_key}")
            flag_str = f"  [{', '.join(flags)}]" if flags else ""
            sample_str = ""
            if col.sample_values:
                samples = ", ".join(f"'{v}'" for v in col.sample_values[:3])
                sample_str = f"  e.g. {samples}"
            lines.append(f"  {col.name}  {col.data_type}{flag_str}{sample_str}")
    return "\n".join(lines)


def get_relevant_schema(
    question: str,
    full_schema: dict[str, TableSchema],
    llm_client: Any,
    model: str,
) -> dict[str, TableSchema]:
    """
    Ask the LLM which tables are relevant for the given question.
    Returns only those tables. Always includes FK-connected tables
    that the selected tables reference.
    """
    import anthropic

    table_list = "\n".join(
        f"- {name}: {', '.join(c.name for c in ts.columns)}"
        for name, ts in full_schema.items()
    )
    prompt = (
        f"Given this database schema:\n{table_list}\n\n"
        f"Which tables are needed to answer this question: \"{question}\"\n\n"
        "Reply with ONLY a comma-separated list of table names, nothing else. "
        "If all tables might be needed, list all."
    )

    try:
        response = llm_client.messages.create(
            model=model,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        selected_names = {t.strip().lower() for t in raw.split(",") if t.strip()}
    except Exception as e:
        log.warning("schema_filter_failed", error=str(e), fallback="full_schema")
        return full_schema

    # Always pull in tables connected by FK to avoid broken joins
    all_referenced: set[str] = set(selected_names)
    for name in list(selected_names):
        if name in full_schema:
            for fk_target in full_schema[name].foreign_keys.values():
                ref_table = fk_target.split(".")[0]
                all_referenced.add(ref_table)

    filtered = {k: v for k, v in full_schema.items() if k in all_referenced}
    excluded = set(full_schema.keys()) - all_referenced

    log.info(
        "schema_filtered",
        question=question[:80],
        included=sorted(filtered.keys()),
        excluded=sorted(excluded),
    )
    return filtered
