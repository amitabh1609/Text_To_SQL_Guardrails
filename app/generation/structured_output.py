from typing import Optional

from pydantic import BaseModel, Field


class SQLGenerationResult(BaseModel):
    sql_query: str = Field(
        description="The generated SQL query. Must be a valid PostgreSQL SELECT statement."
    )
    confidence_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Model's self-assessed confidence (0.0–1.0).",
    )
    reasoning: str = Field(
        description="Step-by-step explanation of how the SQL answers the question."
    )
    tables_used: list[str] = Field(
        description="List of table names referenced in the SQL."
    )
    ambiguity_flags: list[str] = Field(
        default=[],
        description="Any ambiguous parts of the question that required assumptions.",
    )
    cannot_answer: bool = Field(
        default=False,
        description="Set to True if the question cannot be answered with the available schema.",
    )
    cannot_answer_reason: Optional[str] = Field(
        default=None,
        description="If cannot_answer is True, explain why.",
    )
