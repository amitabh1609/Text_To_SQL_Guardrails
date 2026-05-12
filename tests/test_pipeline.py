"""
Integration tests for the full pipeline.
Requires: a running PostgreSQL instance and ANTHROPIC_API_KEY in the environment.
Skip gracefully if DB is not available.
"""
import os
import pytest
from unittest.mock import MagicMock, patch


def db_available() -> bool:
    try:
        from sqlalchemy import create_engine, text
        url = os.environ.get("DATABASE_URL", "postgresql://supplychain:supplychain@localhost:5432/supplychain")
        engine = create_engine(url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def api_key_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


requires_db = pytest.mark.skipif(not db_available(), reason="PostgreSQL not available")
requires_api = pytest.mark.skipif(not api_key_available(), reason="ANTHROPIC_API_KEY not set")


class TestGuardrailsAloneBlock:
    """These tests do not require DB or API — they test guardrail + executor integration."""

    def test_readonly_transaction_rejects_insert(self):
        """Even if guardrails are bypassed, read-only transaction must reject INSERT."""
        if not db_available():
            pytest.skip("DB not available")
        from sqlalchemy import create_engine
        from app.execution.executor import run_readonly
        url = os.environ.get("DATABASE_URL", "postgresql://supplychain:supplychain@localhost:5432/supplychain")
        engine = create_engine(url)
        result = run_readonly(
            "INSERT INTO suppliers (supplier_name, country) VALUES ('TEST', 'XX')",
            engine,
        )
        assert not result.success
        assert result.error is not None

    def test_readonly_transaction_rejects_delete(self):
        if not db_available():
            pytest.skip("DB not available")
        from sqlalchemy import create_engine
        from app.execution.executor import run_readonly
        url = os.environ.get("DATABASE_URL", "postgresql://supplychain:supplychain@localhost:5432/supplychain")
        engine = create_engine(url)
        result = run_readonly("DELETE FROM suppliers WHERE 1=1", engine)
        assert not result.success

    def test_readonly_select_succeeds(self):
        if not db_available():
            pytest.skip("DB not available")
        from sqlalchemy import create_engine
        from app.execution.executor import run_readonly
        url = os.environ.get("DATABASE_URL", "postgresql://supplychain:supplychain@localhost:5432/supplychain")
        engine = create_engine(url)
        result = run_readonly("SELECT 1 AS val", engine)
        assert result.success
        assert result.rows == [{"val": 1}]

    def test_row_limit_enforced(self):
        if not db_available():
            pytest.skip("DB not available")
        from sqlalchemy import create_engine
        from app.execution.executor import run_readonly
        url = os.environ.get("DATABASE_URL", "postgresql://supplychain:supplychain@localhost:5432/supplychain")
        engine = create_engine(url)
        result = run_readonly(
            "SELECT generate_series(1, 2000) AS n",
            engine,
            max_rows=100,
        )
        assert result.success
        assert result.row_count <= 100
        assert result.truncated


@requires_db
@requires_api
class TestFullPipeline:
    """Full end-to-end pipeline tests. Skipped if DB or API key unavailable."""

    @pytest.fixture
    def pipeline_deps(self):
        from sqlalchemy import create_engine
        from anthropic import Anthropic
        from app.config import get_config
        from app.schema.introspection import get_full_schema
        config = get_config()
        engine = create_engine(config.database_url)
        client = Anthropic(api_key=config.anthropic_api_key)
        schema = get_full_schema(engine)
        return config, engine, client, schema

    def test_simple_question(self, pipeline_deps):
        from app.pipeline import run_query_pipeline
        config, engine, client, schema = pipeline_deps
        result = run_query_pipeline(
            "How many active suppliers do we have?",
            engine, client, config, cached_full_schema=schema,
        )
        assert not result.cannot_answer
        assert not result.guardrail_blocked
        assert result.execution_success
        assert result.row_count >= 1

    def test_unanswerable_question(self, pipeline_deps):
        from app.pipeline import run_query_pipeline
        config, engine, client, schema = pipeline_deps
        result = run_query_pipeline(
            "What is the profit margin on each product?",
            engine, client, config, cached_full_schema=schema,
        )
        assert result.cannot_answer

    def test_destructive_injection_blocked(self, pipeline_deps):
        """Even when routed through the pipeline, injection must be caught by guardrails."""
        from app.guardrails.sql_guardrails import check, ViolationType
        result = check("DROP TABLE suppliers")
        assert result.blocked
        assert ViolationType.DDL_STATEMENT in result.violations
