"""
Text-to-SQL with Guardrails — Streamlit UI
"""
import os
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8000")

st.set_page_config(
    page_title="Text-to-SQL with Guardrails",
    page_icon="🛡️",
    layout="wide",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_schema() -> dict | None:
    try:
        r = requests.get(f"{API_BASE}/v1/schema", timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return None


def post_query(question: str, include_reasoning: bool, multi_query: bool) -> dict | None:
    try:
        r = requests.post(
            f"{API_BASE}/v1/query",
            json={
                "question": question,
                "include_reasoning": include_reasoning,
                "multi_query_validation": multi_query,
            },
            timeout=90,
        )
        r.raise_for_status()
        return r.json()
    except requests.exceptions.HTTPError as e:
        st.error(f"API error {e.response.status_code}: {e.response.text[:300]}")
        return None
    except Exception as e:
        st.error(f"Connection error: {e}")
        return None


def confidence_color(score: float) -> str:
    if score >= 0.8:
        return "🟢"
    elif score >= 0.6:
        return "🟡"
    else:
        return "🔴"


# ---------------------------------------------------------------------------
# Sidebar: Schema Explorer
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("🗄️ Schema Explorer")
    schema_data = get_schema()
    if schema_data:
        for table in schema_data.get("tables", []):
            with st.expander(f"**{table['table_name']}** (~{table['row_count_estimate']:,} rows)"):
                for col in table["columns"]:
                    flags = []
                    if col["is_primary_key"]:
                        flags.append("PK")
                    if col.get("foreign_key"):
                        flags.append(f"FK→{col['foreign_key']}")
                    flag_str = f" `[{', '.join(flags)}]`" if flags else ""
                    st.markdown(f"- `{col['name']}` {col['data_type']}{flag_str}")
    else:
        st.warning("Could not reach API. Is the server running?")


# ---------------------------------------------------------------------------
# Main tabs
# ---------------------------------------------------------------------------

tab_query, tab_eval = st.tabs(["🔍 Query", "📊 Eval Dashboard"])

# ============================================================
# TAB 1 — Query
# ============================================================
with tab_query:
    st.title("🛡️ Text-to-SQL with Guardrails")
    st.caption("Natural language interface to your supply chain database — with safety guardrails and hallucination detection.")

    # --- Panel 1: Query Input ---
    with st.form("query_form"):
        question = st.text_area(
            "Ask a question about your supply chain data",
            placeholder="e.g. Which suppliers have an average delivery delay of more than 5 days?",
            height=100,
        )
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            include_reasoning = st.checkbox("Show reasoning", value=False)
        with col2:
            multi_query = st.checkbox("Multi-query validation", value=False)
        with col3:
            submitted = st.form_submit_button("▶ Run Query", type="primary", use_container_width=True)

    if submitted and question.strip():
        with st.spinner("Running pipeline…"):
            resp = post_query(question.strip(), include_reasoning, multi_query)

        if resp:
            # --- Panel 2: Generated SQL ---
            st.subheader("🧾 Generated SQL")
            col_sql, col_conf = st.columns([3, 1])
            with col_sql:
                display_sql = resp.get("sql", "")
                if display_sql:
                    st.code(display_sql, language="sql")
                else:
                    st.info("No SQL generated (question may be unanswerable).")

            with col_conf:
                score = resp.get("confidence_score", 0.0)
                icon = confidence_color(score)
                st.metric("LLM Confidence", f"{icon} {score:.0%}")
                st.caption(f"Latency: {resp.get('latency_ms', 0):.0f} ms")

                tables = resp.get("tables_used", [])
                if tables:
                    st.caption("Tables used:")
                    for t in tables:
                        st.badge(t)

            ambiguity = resp.get("ambiguity_flags", [])
            if ambiguity:
                for flag in ambiguity:
                    st.warning(f"⚠️ Ambiguity: {flag}")

            if resp.get("cannot_answer"):
                st.error(f"❓ Cannot answer: {resp.get('cannot_answer_reason', 'Schema does not support this question.')}")

            if include_reasoning and resp.get("reasoning"):
                with st.expander("💭 LLM Reasoning"):
                    st.write(resp["reasoning"])

            # --- Panel 3: Safety & Validation ---
            st.subheader("🛡️ Safety & Validation")
            col_g, col_bt, col_mq = st.columns(3)

            with col_g:
                gr = resp.get("guardrail", {})
                if gr.get("passed") and not gr.get("blocked"):
                    st.success("✅ Guardrail PASSED")
                else:
                    st.error("❌ Guardrail BLOCKED")
                    for v in gr.get("violations", []):
                        st.caption(f"• {v}")

            with col_bt:
                bt = resp.get("back_translation")
                if bt:
                    sim = bt.get("similarity_score", 0)
                    suspected = bt.get("hallucination_suspected", False)
                    if suspected:
                        st.warning(f"⚠️ Hallucination suspected\nSimilarity: {sim:.2f}")
                    else:
                        st.success(f"✅ Back-translation OK\nSimilarity: {sim:.2f}")
                    with st.expander("Back-translated question"):
                        st.write(bt.get("back_translated_question", ""))
                else:
                    st.caption("Back-translation not run")

            with col_mq:
                agreement = resp.get("multi_query_agreement")
                if agreement:
                    if agreement == "AGREEMENT":
                        st.success(f"✅ Multi-query: {agreement}")
                    elif agreement == "PARTIAL_AGREEMENT":
                        st.warning(f"⚠️ Multi-query: {agreement}")
                    else:
                        st.error(f"❌ Multi-query: {agreement}")
                else:
                    st.caption("Multi-query not enabled" if not multi_query else "Multi-query not triggered")

            # --- Panel 4: Results ---
            st.subheader("📋 Query Results")
            results = resp.get("results")
            if results is not None and len(results) > 0:
                df = pd.DataFrame(results)
                st.dataframe(df, use_container_width=True)
                st.caption(f"{resp.get('row_count', 0)} rows returned")
            elif resp.get("cannot_answer"):
                pass  # Already shown above
            elif resp.get("guardrail", {}).get("blocked"):
                st.error("Query was blocked by guardrail — no results.")
            else:
                st.info("No results returned (query may have returned 0 rows).")

    elif submitted:
        st.warning("Please enter a question.")


# ============================================================
# TAB 2 — Eval Dashboard
# ============================================================
with tab_eval:
    st.title("📊 Eval Dashboard")
    results_path = Path(__file__).parent.parent / "eval" / "results" / "latest_results.md"
    if results_path.exists():
        content = results_path.read_text()
        st.markdown(content)
    else:
        st.info(
            "No eval results found yet. Run `make eval` to generate results.\n\n"
            "Expected at: `eval/results/latest_results.md`"
        )
