import time
from dataclasses import dataclass

import structlog
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

log = structlog.get_logger(__name__)

_MAX_ROWS = 1000


@dataclass
class ExecutionResult:
    success: bool
    rows: list[dict]
    row_count: int
    error: str | None
    latency_ms: float
    truncated: bool


def run_readonly(
    sql: str,
    engine: Engine,
    max_rows: int = _MAX_ROWS,
) -> ExecutionResult:
    """
    Execute sql inside a read-only transaction.
    Defense-in-depth: even if guardrails miss something, the DB will reject writes.
    Rolls back after every execution regardless of success/failure.
    """
    t0 = time.perf_counter()
    rows: list[dict] = []
    error: str | None = None
    truncated = False

    try:
        with engine.connect() as conn:
            conn.execute(text("BEGIN"))
            conn.execute(text("SET TRANSACTION READ ONLY"))
            try:
                result = conn.execute(text(sql))
                column_keys = list(result.keys())
                all_rows = result.fetchmany(max_rows + 1)
                if len(all_rows) > max_rows:
                    all_rows = all_rows[:max_rows]
                    truncated = True
                rows = [dict(zip(column_keys, row)) for row in all_rows]
            finally:
                conn.execute(text("ROLLBACK"))
    except SQLAlchemyError as e:
        error = str(e).split("\n")[0]  # First line only — avoid leaking full trace
        log.warning("execution_error", error=error, sql=sql[:200])
    except Exception as e:
        error = f"Unexpected error: {type(e).__name__}: {str(e)[:200]}"
        log.error("execution_unexpected_error", error=str(e))

    latency_ms = (time.perf_counter() - t0) * 1000

    result_obj = ExecutionResult(
        success=error is None,
        rows=rows,
        row_count=len(rows),
        error=error,
        latency_ms=round(latency_ms, 1),
        truncated=truncated,
    )
    log.info(
        "execution_complete",
        success=result_obj.success,
        row_count=result_obj.row_count,
        truncated=truncated,
        latency_ms=round(latency_ms, 1),
    )
    return result_obj
