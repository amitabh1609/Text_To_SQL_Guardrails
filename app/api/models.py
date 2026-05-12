from typing import Any, Optional

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3, description="Natural language question about the supply chain data.")
    include_reasoning: bool = Field(False, description="Include LLM's step-by-step reasoning in the response.")
    multi_query_validation: bool = Field(False, description="Run multi-query validation for complex questions.")


class GuardrailInfo(BaseModel):
    passed: bool
    violations: list[str]
    blocked: bool
    violation_details: list[str]


class BackTranslationInfo(BaseModel):
    back_translated_question: str
    similarity_score: float
    hallucination_suspected: bool
    confidence_level: str


class QueryResponse(BaseModel):
    question: str
    sql: str
    results: Optional[list[dict[str, Any]]]
    row_count: int
    confidence_score: float
    guardrail: GuardrailInfo
    hallucination_suspected: bool
    back_translation: Optional[BackTranslationInfo]
    multi_query_agreement: Optional[str]
    reasoning: Optional[str]
    tables_used: list[str]
    ambiguity_flags: list[str]
    cannot_answer: bool
    cannot_answer_reason: Optional[str]
    latency_ms: float
    schema_tables_filtered_out: list[str]


class HealthResponse(BaseModel):
    status: str
    database: str
    model: str


class ColumnDetail(BaseModel):
    name: str
    data_type: str
    nullable: bool
    is_primary_key: bool
    foreign_key: Optional[str]
    sample_values: list[str]


class TableDetail(BaseModel):
    table_name: str
    row_count_estimate: int
    columns: list[ColumnDetail]


class SchemaResponse(BaseModel):
    tables: list[TableDetail]
