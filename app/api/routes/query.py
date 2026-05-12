import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Engine, text

from app.api.models import (
    BackTranslationInfo,
    ColumnDetail,
    GuardrailInfo,
    HealthResponse,
    QueryRequest,
    QueryResponse,
    SchemaResponse,
    TableDetail,
)
from app.api.deps import get_anthropic_client, get_config, get_db_engine, get_full_schema_cached
from app.pipeline import run_query_pipeline

log = structlog.get_logger(__name__)
router = APIRouter()


@router.post("/v1/query", response_model=QueryResponse, summary="Execute a natural language query")
def query_endpoint(
    body: QueryRequest,
    engine: Engine = Depends(get_db_engine),
    anthropic_client=Depends(get_anthropic_client),
    config=Depends(get_config),
    full_schema=Depends(get_full_schema_cached),
):
    log.info("query_received", question=body.question[:100])
    result = run_query_pipeline(
        question=body.question,
        db_engine=engine,
        anthropic_client=anthropic_client,
        config=config,
        enable_multi_query=body.multi_query_validation,
        cached_full_schema=full_schema,
    )

    bt_info = None
    if result.back_translation_result:
        bt = result.back_translation_result
        bt_info = BackTranslationInfo(
            back_translated_question=bt.back_translated_question,
            similarity_score=bt.similarity_score,
            hallucination_suspected=bt.hallucination_suspected,
            confidence_level=bt.confidence_level,
        )

    return QueryResponse(
        question=result.question,
        sql=result.generated_sql,
        results=result.results,
        row_count=result.row_count,
        confidence_score=result.llm_confidence_score,
        guardrail=GuardrailInfo(
            passed=result.guardrail_passed,
            violations=result.guardrail_violations,
            blocked=result.guardrail_blocked,
            violation_details=[],
        ),
        hallucination_suspected=(
            result.back_translation_result.hallucination_suspected
            if result.back_translation_result else False
        ),
        back_translation=bt_info,
        multi_query_agreement=result.multi_query_agreement,
        reasoning=result.llm_reasoning if body.include_reasoning else None,
        tables_used=result.tables_used,
        ambiguity_flags=result.ambiguity_flags,
        cannot_answer=result.cannot_answer,
        cannot_answer_reason=result.cannot_answer_reason,
        latency_ms=result.total_latency_ms,
        schema_tables_filtered_out=result.schema_tables_filtered_out,
    )


@router.get("/v1/health", response_model=HealthResponse, summary="Health check")
def health(
    engine: Engine = Depends(get_db_engine),
    config=Depends(get_config),
):
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {e}"
    return HealthResponse(status="ok", database=db_status, model=config.llm_model)


@router.get("/v1/schema", response_model=SchemaResponse, summary="Get full database schema")
def get_schema(full_schema=Depends(get_full_schema_cached)):
    tables = [
        TableDetail(
            table_name=ts.table_name,
            row_count_estimate=ts.row_count_estimate,
            columns=[
                ColumnDetail(
                    name=c.name,
                    data_type=c.data_type,
                    nullable=c.nullable,
                    is_primary_key=c.is_primary_key,
                    foreign_key=c.foreign_key,
                    sample_values=c.sample_values,
                )
                for c in ts.columns
            ],
        )
        for ts in full_schema.values()
    ]
    return SchemaResponse(tables=tables)
