import time
from dataclasses import dataclass
from typing import Any

import structlog
from anthropic import Anthropic

from app.generation.prompts import MULTI_QUERY_SYSTEM
from app.schema.introspection import TableSchema, schema_to_prompt_text

log = structlog.get_logger(__name__)

AgreementLevel = str  # "AGREEMENT" | "PARTIAL_AGREEMENT" | "DIVERGENCE"


@dataclass
class MultiQueryResult:
    primary_sql: str
    alternative_sql: str
    primary_row_count: int | None
    alternative_row_count: int | None
    agreement: AgreementLevel
    details: str


def generate_alternative_sql(
    question: str,
    primary_sql: str,
    filtered_schema: dict[str, TableSchema],
    anthropic_client: Anthropic,
    model: str,
) -> str:
    schema_text = schema_to_prompt_text(filtered_schema)
    prompt = (
        f"Database schema:\n{schema_text}\n\n"
        f"Question: {question}\n\n"
        f"First SQL approach:\n```sql\n{primary_sql}\n```\n\n"
        "Generate a DIFFERENT SQL query that produces the same result using different techniques "
        "(e.g., use a CTE instead of a subquery, or a different join order, or window functions). "
        "Output only the SQL query, no explanation."
    )
    response = anthropic_client.messages.create(
        model=model,
        max_tokens=1024,
        system=MULTI_QUERY_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()
    # Strip markdown fences if present
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1]) if len(lines) > 2 else raw
    return raw


def compare_results(
    primary_rows: list[dict],
    alt_rows: list[dict],
) -> tuple[AgreementLevel, str]:
    p_count = len(primary_rows)
    a_count = len(alt_rows)

    if p_count == 0 and a_count == 0:
        return "AGREEMENT", "Both queries returned zero rows."

    if p_count != a_count:
        return "DIVERGENCE", (
            f"Row count mismatch: primary={p_count}, alternative={a_count}."
        )

    # Compare sets of row values (order-independent)
    def row_to_frozenset(row: dict) -> frozenset:
        return frozenset((k, str(v)) for k, v in row.items())

    primary_set = {row_to_frozenset(r) for r in primary_rows}
    alt_set = {row_to_frozenset(r) for r in alt_rows}

    if primary_set == alt_set:
        return "AGREEMENT", f"Both queries returned identical {p_count} rows."

    # Same count, different values
    overlap = len(primary_set & alt_set)
    pct = overlap / max(len(primary_set), 1) * 100
    if pct >= 90:
        return "PARTIAL_AGREEMENT", (
            f"{overlap}/{max(len(primary_set), 1)} rows overlap ({pct:.0f}%). "
            "Minor differences — review recommended."
        )
    return "DIVERGENCE", (
        f"Significant result divergence: only {overlap} rows overlap out of {p_count}."
    )


def validate_multi_query(
    question: str,
    primary_sql: str,
    primary_results: list[dict],
    filtered_schema: dict[str, TableSchema],
    anthropic_client: Anthropic,
    model: str,
    executor_fn: Any,
) -> tuple[MultiQueryResult, float]:
    """
    Generate an alternative SQL and compare results. executor_fn takes a SQL string
    and returns list[dict]. Returns (MultiQueryResult, latency_ms).
    """
    t0 = time.perf_counter()

    try:
        alt_sql = generate_alternative_sql(
            question, primary_sql, filtered_schema, anthropic_client, model
        )
        alt_results = executor_fn(alt_sql)
        agreement, details = compare_results(primary_results, alt_results)
        alt_count = len(alt_results)
    except Exception as e:
        log.warning("multi_query_failed", error=str(e))
        alt_sql = ""
        alt_count = None
        agreement = "DIVERGENCE"
        details = f"Alternative query generation or execution failed: {e}"
        alt_results = []

    latency_ms = (time.perf_counter() - t0) * 1000

    result = MultiQueryResult(
        primary_sql=primary_sql,
        alternative_sql=alt_sql,
        primary_row_count=len(primary_results),
        alternative_row_count=alt_count,
        agreement=agreement,
        details=details,
    )
    log.info(
        "multi_query_validation",
        agreement=agreement,
        primary_rows=len(primary_results),
        alt_rows=alt_count,
        latency_ms=round(latency_ms, 1),
    )
    return result, latency_ms
