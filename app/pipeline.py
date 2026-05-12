import time
from dataclasses import dataclass, field

import structlog
from anthropic import Anthropic
from sqlalchemy import Engine

from app.config import AppConfig
from app.execution.executor import ExecutionResult, run_readonly
from app.generation.prompts import is_complex_question
from app.generation.sql_generator import build_instructor_client, generate_sql
from app.guardrails.sql_guardrails import GuardrailResult, check as guardrail_check
from app.schema.introspection import (
    TableSchema,
    get_full_schema,
    get_relevant_schema,
)
from app.validation.back_translation import BackTranslationResult, check_back_translation
from app.validation.multi_query import MultiQueryResult, validate_multi_query

log = structlog.get_logger(__name__)


@dataclass
class QueryPipelineResult:
    question: str
    generated_sql: str
    results: list[dict] | None
    row_count: int
    execution_success: bool
    execution_error: str | None

    guardrail_passed: bool
    guardrail_violations: list[str]
    guardrail_blocked: bool

    back_translation_result: BackTranslationResult | None
    multi_query_result: MultiQueryResult | None
    multi_query_agreement: str | None

    llm_confidence_score: float
    llm_reasoning: str
    tables_used: list[str]
    ambiguity_flags: list[str]
    cannot_answer: bool
    cannot_answer_reason: str | None
    schema_tables_filtered_out: list[str]

    total_latency_ms: float
    schema_filter_latency_ms: float
    generation_latency_ms: float
    validation_latency_ms: float
    execution_latency_ms: float


def run_query_pipeline(
    question: str,
    db_engine: Engine,
    anthropic_client: Anthropic,
    config: AppConfig,
    enable_multi_query: bool = False,
    cached_full_schema: dict[str, TableSchema] | None = None,
) -> QueryPipelineResult:
    pipeline_start = time.perf_counter()

    # -------------------------------------------------------------------------
    # Step 1: Schema Filtering
    # -------------------------------------------------------------------------
    t0 = time.perf_counter()
    full_schema = cached_full_schema or get_full_schema(db_engine)
    filtered_schema = get_relevant_schema(
        question, full_schema, anthropic_client, config.llm_model
    )
    schema_filter_ms = (time.perf_counter() - t0) * 1000
    filtered_out = [t for t in full_schema if t not in filtered_schema]
    log.info("step_schema_filter", included=list(filtered_schema.keys()), excluded=filtered_out)

    # -------------------------------------------------------------------------
    # Step 2: SQL Generation
    # -------------------------------------------------------------------------
    t0 = time.perf_counter()
    instructor_client = build_instructor_client(anthropic_client)
    gen_result, gen_latency_ms = generate_sql(
        question, filtered_schema, instructor_client, config.llm_model
    )
    log.info("step_sql_generation", cannot_answer=gen_result.cannot_answer)

    if gen_result.cannot_answer:
        total_ms = (time.perf_counter() - pipeline_start) * 1000
        return QueryPipelineResult(
            question=question,
            generated_sql="",
            results=None,
            row_count=0,
            execution_success=False,
            execution_error=gen_result.cannot_answer_reason,
            guardrail_passed=True,
            guardrail_violations=[],
            guardrail_blocked=False,
            back_translation_result=None,
            multi_query_result=None,
            multi_query_agreement=None,
            llm_confidence_score=gen_result.confidence_score,
            llm_reasoning=gen_result.reasoning,
            tables_used=gen_result.tables_used,
            ambiguity_flags=gen_result.ambiguity_flags,
            cannot_answer=True,
            cannot_answer_reason=gen_result.cannot_answer_reason,
            schema_tables_filtered_out=filtered_out,
            total_latency_ms=round(total_ms, 1),
            schema_filter_latency_ms=round(schema_filter_ms, 1),
            generation_latency_ms=round(gen_latency_ms, 1),
            validation_latency_ms=0.0,
            execution_latency_ms=0.0,
        )

    sql = gen_result.sql_query

    # -------------------------------------------------------------------------
    # Step 3: Guardrail Check
    # -------------------------------------------------------------------------
    guardrail_result: GuardrailResult = guardrail_check(sql)
    log.info("step_guardrail", passed=guardrail_result.passed, blocked=guardrail_result.blocked)

    if guardrail_result.blocked:
        total_ms = (time.perf_counter() - pipeline_start) * 1000
        return QueryPipelineResult(
            question=question,
            generated_sql=sql,
            results=None,
            row_count=0,
            execution_success=False,
            execution_error="Blocked by guardrail: " + "; ".join(guardrail_result.violation_details),
            guardrail_passed=False,
            guardrail_violations=[v.value for v in guardrail_result.violations],
            guardrail_blocked=True,
            back_translation_result=None,
            multi_query_result=None,
            multi_query_agreement=None,
            llm_confidence_score=gen_result.confidence_score,
            llm_reasoning=gen_result.reasoning,
            tables_used=gen_result.tables_used,
            ambiguity_flags=gen_result.ambiguity_flags,
            cannot_answer=False,
            cannot_answer_reason=None,
            schema_tables_filtered_out=filtered_out,
            total_latency_ms=round(total_ms, 1),
            schema_filter_latency_ms=round(schema_filter_ms, 1),
            generation_latency_ms=round(gen_latency_ms, 1),
            validation_latency_ms=0.0,
            execution_latency_ms=0.0,
        )

    safe_sql = guardrail_result.sanitised_sql or sql

    # -------------------------------------------------------------------------
    # Step 4: Execution (needed before multi-query which requires primary results)
    # -------------------------------------------------------------------------
    exec_result: ExecutionResult = run_readonly(safe_sql, db_engine, config.max_rows)
    execution_ms = exec_result.latency_ms
    log.info("step_execution", success=exec_result.success, rows=exec_result.row_count)

    # -------------------------------------------------------------------------
    # Step 5: Hallucination Detection
    # -------------------------------------------------------------------------
    t0 = time.perf_counter()
    bt_result: BackTranslationResult | None = None
    mq_result: MultiQueryResult | None = None

    try:
        bt_result, _ = check_back_translation(
            question, safe_sql, anthropic_client, config.llm_model,
            threshold=config.back_translation_threshold,
        )
    except Exception as e:
        log.warning("back_translation_error", error=str(e))

    if enable_multi_query and is_complex_question(question) and exec_result.success:
        def executor_fn(s: str) -> list[dict]:
            from app.guardrails.sql_guardrails import check as gc
            gr = gc(s)
            if gr.blocked:
                return []
            return run_readonly(gr.sanitised_sql or s, db_engine, config.max_rows).rows

        try:
            mq_result, _ = validate_multi_query(
                question, safe_sql, exec_result.rows, filtered_schema,
                anthropic_client, config.llm_model, executor_fn,
            )
        except Exception as e:
            log.warning("multi_query_error", error=str(e))

    validation_ms = (time.perf_counter() - t0) * 1000

    # -------------------------------------------------------------------------
    # Step 6: Assemble Result
    # -------------------------------------------------------------------------
    total_ms = (time.perf_counter() - pipeline_start) * 1000
    return QueryPipelineResult(
        question=question,
        generated_sql=safe_sql,
        results=exec_result.rows if exec_result.success else None,
        row_count=exec_result.row_count,
        execution_success=exec_result.success,
        execution_error=exec_result.error,
        guardrail_passed=guardrail_result.passed,
        guardrail_violations=[v.value for v in guardrail_result.violations],
        guardrail_blocked=False,
        back_translation_result=bt_result,
        multi_query_result=mq_result,
        multi_query_agreement=mq_result.agreement if mq_result else None,
        llm_confidence_score=gen_result.confidence_score,
        llm_reasoning=gen_result.reasoning,
        tables_used=gen_result.tables_used,
        ambiguity_flags=gen_result.ambiguity_flags,
        cannot_answer=False,
        cannot_answer_reason=None,
        schema_tables_filtered_out=filtered_out,
        total_latency_ms=round(total_ms, 1),
        schema_filter_latency_ms=round(schema_filter_ms, 1),
        generation_latency_ms=round(gen_latency_ms, 1),
        validation_latency_ms=round(validation_ms, 1),
        execution_latency_ms=round(execution_ms, 1),
    )
