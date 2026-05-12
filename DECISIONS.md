# Architecture Decision Records

## ADR-001: PostgreSQL over DuckDB

**Decision:** Use PostgreSQL 15 via Docker rather than DuckDB for the query sandbox.

**Reasoning:** DuckDB is excellent for analytics workloads and would simplify local setup, but it does not provide the database-level safety primitive we need: `SET TRANSACTION READ ONLY`. In PostgreSQL, this is enforced by the database engine itself — no amount of cleverness in the application layer can override it. If the guardrail layer ever fails to catch a destructive query, the read-only transaction is the last line of defense that the database itself enforces. DuckDB has no equivalent mechanism. For a system whose headline feature is safety, this is a non-negotiable.

**Trade-off:** PostgreSQL requires Docker and more setup overhead. Accepted.

---

## ADR-002: `instructor` over raw LLM output parsing

**Decision:** All structured LLM outputs use the `instructor` library with Pydantic v2 models. No regex or string parsing on raw LLM text.

**Reasoning:** Raw LLM output is non-deterministic. The model may return SQL inside a markdown code fence, with trailing explanation text, or with inconsistent JSON keys. Parsing this with regex creates fragile code that breaks on minor model version changes. `instructor` enforces the schema at the API call level — if the model returns malformed output, it retries automatically. The failure mode is loud (exception) rather than silent (wrong data silently passed downstream).

**Trade-off:** `instructor` adds latency for retries on malformed outputs. Acceptable since correctness > raw speed for this use case.

---

## ADR-003: Back-translation as primary hallucination detection

**Decision:** Use back-translation (SQL → question → similarity score) as the primary hallucination signal, not execution comparison alone.

**Reasoning:** Execution comparison only catches queries that return wrong results. A query can be semantically wrong but accidentally return plausible-looking data — for example, `SELECT * FROM products ORDER BY unit_cost DESC LIMIT 5` when the question asked for products *below* reorder level. Execution would "succeed" with results, but the SQL answers a completely different question. Back-translation catches this class of error because it compares what the question asked to what the SQL actually answers, independently of whether the SQL executes cleanly.

**Trade-off:** Back-translation adds ~500–1000ms latency per query (LLM call + embedding). Acceptable given the safety/correctness goal. Also introduces false positives at strict thresholds — tuned down to 0.75 after finding 0.85 flagged ~30% of correct queries.

---

## ADR-004: `sqlparse` AST over regex for guardrail detection

**Decision:** All SQL guardrail checks use `sqlparse` abstract syntax tree parsing. No regex applied to raw SQL strings for keyword detection.

**Reasoning:** Regex on SQL strings is trivially gameable and produces false positives. A query like `SELECT * FROM create_table_log WHERE drop_date > '2024-01-01'` would match a naive `CREATE|DROP` regex and be incorrectly blocked. More subtly, a query like `SELECT -- DROP TABLE users` with a comment could fool some parsers. `sqlparse` parses the token stream and identifies keyword types (DDL, DML, function calls) from the AST, not from substring matching. This correctly handles table names, column names, and string literals that happen to contain SQL keywords.

**Failure discovered and fixed:** First implementation used `re.search(r'\bDROP\b', sql, re.IGNORECASE)` — correctly blocked destructive queries but also blocked `SELECT * FROM drop_shipment_log`. Switched to sqlparse token type checking. All unit tests in `tests/test_guardrails.py` verify this behavior.

---

## ADR-005: Schema filtering accuracy vs. completeness trade-off

**Decision:** Dynamically filter the schema to only include tables relevant to the question before constructing the SQL generation prompt.

**Reasoning:** Sending the full schema (all 6 tables, all columns, all FK relationships) for every query inflates the prompt and increases hallucination. The model may reference columns from tables that aren't needed, or confuse similar column names across tables. Dynamic filtering reduces this noise.

**Risk:** If the schema filter incorrectly excludes a needed table, the generated SQL will be wrong — possibly silently wrong (it executes but answers a different question). Mitigation: (1) FK-connected tables are always included alongside selected tables, preventing broken join errors; (2) if the filtered schema causes a SQL error, the back-translation similarity will drop, flagging the result.

**Failure discovered:** Early implementation excluded `suppliers` when asking "Which products were ordered from Indian suppliers?" because the question mentioned products more prominently. Fixed by always pulling in FK-linked tables — `purchase_orders` links to `suppliers`, so `suppliers` gets pulled in automatically.

---

## ADR-006: 50 hand-curated eval questions, not LLM-generated

**Decision:** All 50 golden dataset questions are hand-written. No LLM was used to generate them.

**Reasoning:** LLM-generated eval questions carry the same systematic biases as the model being evaluated. If Claude tends to interpret "best supplier" as "highest rating", it will generate eval questions that phrase it that way — and then correctly answer those questions, inflating the eval score. Human curation ensures adversarial coverage: ambiguous phrasing, unanswerable questions that look answerable, date arithmetic edge cases, and questions that require complex multi-table reasoning. The 6 unanswerable questions are particularly important — they test the hardest failure mode (the system confidently returning wrong SQL instead of saying "I cannot answer this").
