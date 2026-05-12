import time
from typing import Any

import instructor
import structlog
from anthropic import Anthropic

from app.generation.prompts import SQL_GENERATION_SYSTEM
from app.generation.structured_output import SQLGenerationResult
from app.schema.introspection import TableSchema, schema_to_prompt_text

log = structlog.get_logger(__name__)


def build_instructor_client(anthropic_client: Anthropic) -> Any:
    return instructor.from_anthropic(anthropic_client)


def generate_sql(
    question: str,
    filtered_schema: dict[str, TableSchema],
    instructor_client: Any,
    model: str,
) -> tuple[SQLGenerationResult, float]:
    """
    Generate SQL for a natural language question using instructor-enforced structured output.
    Returns (SQLGenerationResult, latency_ms).
    """
    schema_text = schema_to_prompt_text(filtered_schema)
    user_message = (
        f"Database schema:\n{schema_text}\n\n"
        f"Question: {question}\n\n"
        "Generate a PostgreSQL SELECT query to answer this question. "
        "If the question cannot be answered with the schema, set cannot_answer=True."
    )

    t0 = time.perf_counter()
    result: SQLGenerationResult = instructor_client.messages.create(
        model=model,
        max_tokens=2048,
        system=SQL_GENERATION_SYSTEM,
        messages=[{"role": "user", "content": user_message}],
        response_model=SQLGenerationResult,
    )
    latency_ms = (time.perf_counter() - t0) * 1000

    log.info(
        "sql_generated",
        question=question[:80],
        cannot_answer=result.cannot_answer,
        confidence=result.confidence_score,
        tables=result.tables_used,
        latency_ms=round(latency_ms, 1),
    )
    return result, latency_ms
