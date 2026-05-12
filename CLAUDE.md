# Text-to-SQL with Guardrails & Hallucination Detection
# Amitabh Choudhury — Portfolio Project 3

## Project Identity
This is a production-grade AI portfolio project, not a tutorial.
Every component must work exactly as designed. No mocking, no stubs left in production paths, no "TODO: implement later".

## Stack (Do Not Deviate)
- Python 3.11, uv for dependency management (pyproject.toml only, no requirements.txt)
- PostgreSQL 15 via Docker
- Claude Sonnet `claude-sonnet-4-20250514` via Anthropic API
- `instructor` library for ALL structured LLM outputs — never parse raw LLM text with regex
- Pydantic v2 syntax only (model_validator, field_validator — no v1 @validator)
- SQLAlchemy 2.x for all DB access
- `sqlparse` for SQL parsing in guardrails — never regex on raw SQL strings
- FastAPI for the API layer
- Streamlit for the UI
- `structlog` for all logging — no bare print() statements

## Non-Negotiable Rules
- The guardrail layer uses sqlparse AST parsing, not regex
- Every LLM call that returns structured data goes through instructor
- All DB execution runs inside SET TRANSACTION READ ONLY
- Type hints on every function signature
- All Pydantic models use v2 syntax

## Build Order
Follow this exactly. Do not skip ahead or build in parallel:
1. docker-compose.yml + db/init.sql
2. db/seed.py (500+ rows per table)
3. app/config.py + app/schema/introspection.py
4. app/guardrails/sql_guardrails.py + tests/test_guardrails.py
5. app/generation/structured_output.py + app/generation/sql_generator.py
6. app/validation/back_translation.py
7. app/validation/multi_query.py
8. app/execution/executor.py
9. app/pipeline.py
10. app/api/
11. eval/golden_dataset.json + eval/run_evals.py
12. ui/streamlit_app.py
13. Makefile
14. DECISIONS.md
15. README.md (last)

## Eval Pass Criteria
The project is not done until make eval shows:
- Execution accuracy >= 70% on 50-question golden dataset
- 100% block rate on all 10 destructive injection tests
- Zero unsafe queries executed (non-negotiable)
- Back-translation F1 >= 0.70

## Database Domain
Supply chain / inventory. Tables: suppliers, products, warehouses, inventory, purchase_orders, shipments.

## What "Done" Means for Each Step
After each build step, run the relevant test or make command before proceeding.
Never move to the next step with a broken previous step.

## README
Write last. Never fabricate metrics — use placeholders like [INSERT METRIC] if eval hasn't run yet.
