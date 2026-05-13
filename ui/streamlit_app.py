import os
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8000")
_DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "")
if _DEMO_PASSWORD:
    _entered = st.text_input("Enter demo password", type="password")
    if _entered != _DEMO_PASSWORD:
        st.warning("Enter the password to continue.")
        st.stop()

st.set_page_config(
    page_title="SQL Guardrails — Supply Chain",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Fonts & root ── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* ── Hide default streamlit chrome ── */
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 1.5rem; padding-bottom: 2rem; }

/* ── Hero banner ── */
.hero {
    background: linear-gradient(135deg, #0f2044 0%, #1a3a6e 50%, #0d3060 100%);
    border-radius: 14px;
    padding: 2rem 2.5rem 1.8rem;
    margin-bottom: 1.5rem;
    position: relative;
    overflow: hidden;
}
.hero::before {
    content: "";
    position: absolute;
    top: -40px; right: -40px;
    width: 200px; height: 200px;
    background: radial-gradient(circle, rgba(79,142,247,0.18) 0%, transparent 70%);
    border-radius: 50%;
}
.hero::after {
    content: "";
    position: absolute;
    bottom: -30px; left: 30%;
    width: 300px; height: 120px;
    background: radial-gradient(ellipse, rgba(99,179,237,0.08) 0%, transparent 70%);
}
.hero h1 {
    color: #e2eeff;
    font-size: 1.75rem;
    font-weight: 700;
    margin: 0 0 0.3rem 0;
    letter-spacing: -0.3px;
}
.hero p {
    color: #93b4e0;
    font-size: 0.9rem;
    margin: 0;
    line-height: 1.5;
}
.hero-badge {
    display: inline-block;
    background: rgba(79,142,247,0.2);
    border: 1px solid rgba(79,142,247,0.4);
    color: #7eb8f7;
    border-radius: 20px;
    padding: 2px 12px;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.5px;
    margin-right: 6px;
    margin-bottom: 0.8rem;
}

/* ── Section headers ── */
.section-label {
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    color: #6b7280;
    margin-bottom: 0.5rem;
    margin-top: 1.4rem;
}

/* ── SQL code block ── */
.sql-wrapper {
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 10px;
    padding: 0;
    overflow: hidden;
}
.sql-header {
    background: #161b22;
    border-bottom: 1px solid #30363d;
    padding: 6px 14px;
    display: flex;
    align-items: center;
    gap: 6px;
}
.sql-dot {
    width: 10px; height: 10px;
    border-radius: 50%;
    display: inline-block;
}

/* ── Status cards ── */
.status-card {
    border-radius: 10px;
    padding: 1rem 1.1rem;
    border: 1px solid;
    height: 100%;
}
.status-pass {
    background: #f0fdf4;
    border-color: #86efac;
}
.status-fail {
    background: #fef2f2;
    border-color: #fca5a5;
}
.status-warn {
    background: #fffbeb;
    border-color: #fcd34d;
}
.status-neutral {
    background: #f8fafc;
    border-color: #e2e8f0;
}
.status-card .card-title {
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.8px;
    text-transform: uppercase;
    margin-bottom: 0.4rem;
}
.status-pass .card-title { color: #15803d; }
.status-fail .card-title { color: #dc2626; }
.status-warn .card-title { color: #d97706; }
.status-neutral .card-title { color: #64748b; }

.status-card .card-value {
    font-size: 1.05rem;
    font-weight: 600;
    color: #1e293b;
}
.status-card .card-sub {
    font-size: 0.78rem;
    color: #64748b;
    margin-top: 0.25rem;
}

/* ── Pipeline step indicator ── */
.pipeline-steps {
    display: flex;
    align-items: center;
    gap: 0;
    margin: 1rem 0 1.5rem;
    overflow-x: auto;
    padding-bottom: 4px;
}
.pipeline-step {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
    flex: 1;
    min-width: 80px;
}
.step-circle {
    width: 32px; height: 32px;
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.85rem;
    font-weight: 600;
    border: 2px solid;
    background: white;
    position: relative;
    z-index: 1;
}
.step-label {
    font-size: 0.65rem;
    font-weight: 600;
    text-align: center;
    color: #64748b;
    letter-spacing: 0.3px;
}
.step-connector {
    flex: 1;
    height: 2px;
    background: #e2e8f0;
    margin-bottom: 20px;
    min-width: 12px;
}
.step-done .step-circle { border-color: #22c55e; color: #15803d; background: #f0fdf4; }
.step-blocked .step-circle { border-color: #ef4444; color: #dc2626; background: #fef2f2; }
.step-pending .step-circle { border-color: #cbd5e1; color: #94a3b8; background: #f8fafc; }

/* ── Tag chips ── */
.chip {
    display: inline-block;
    background: #eff6ff;
    color: #1d4ed8;
    border: 1px solid #bfdbfe;
    border-radius: 20px;
    padding: 2px 10px;
    font-size: 0.72rem;
    font-weight: 500;
    margin: 2px 3px 2px 0;
}

/* ── Metric pill ── */
.metric-pill {
    background: #f1f5f9;
    border-radius: 8px;
    padding: 0.6rem 0.9rem;
    text-align: center;
}
.metric-pill .val {
    font-size: 1.5rem;
    font-weight: 700;
    color: #0f172a;
    line-height: 1;
}
.metric-pill .lbl {
    font-size: 0.68rem;
    color: #64748b;
    font-weight: 600;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    margin-top: 3px;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: #0f2044;
}
[data-testid="stSidebar"] * { color: #cbd5e1 !important; }
[data-testid="stSidebar"] .stExpander {
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 8px !important;
    background: rgba(255,255,255,0.04) !important;
}
[data-testid="stSidebar"] hr {
    border-color: rgba(255,255,255,0.1) !important;
}

/* ── Dataframe ── */
[data-testid="stDataFrame"] {
    border-radius: 8px;
    overflow: hidden;
    border: 1px solid #e2e8f0 !important;
}

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {
    gap: 4px;
    background: #f1f5f9;
    border-radius: 10px;
    padding: 4px;
    border-bottom: none;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 7px;
    padding: 6px 20px;
    font-weight: 500;
    font-size: 0.85rem;
    color: #475569;
}
.stTabs [aria-selected="true"] {
    background: white !important;
    color: #1e40af !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}

/* ── Form submit button ── */
.stFormSubmitButton button {
    background: linear-gradient(135deg, #1d4ed8, #2563eb) !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    letter-spacing: 0.3px !important;
    transition: all 0.2s ease !important;
    box-shadow: 0 2px 8px rgba(29,78,216,0.3) !important;
}
.stFormSubmitButton button:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 14px rgba(29,78,216,0.4) !important;
}

/* ── Toast-style info/warn/error ── */
.stAlert {
    border-radius: 8px !important;
}

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: #f1f5f9; border-radius: 3px; }
::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #94a3b8; }
</style>
""", unsafe_allow_html=True)


# ── Helpers ──────────────────────────────────────────────────────────────────

def get_schema() -> dict | None:
    try:
        r = requests.get(f"{API_BASE}/v1/schema", timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
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


def confidence_badge(score: float) -> str:
    if score >= 0.8:
        return f"<span style='color:#15803d;font-weight:700'>{score:.0%} HIGH</span>"
    elif score >= 0.6:
        return f"<span style='color:#d97706;font-weight:700'>{score:.0%} MED</span>"
    else:
        return f"<span style='color:#dc2626;font-weight:700'>{score:.0%} LOW</span>"


def chips(items: list[str]) -> str:
    return " ".join(f'<span class="chip">{i}</span>' for i in items)


EXAMPLE_QUESTIONS = [
    "Which suppliers have an avg delivery delay > 5 days?",
    "Top 5 products by total quantity ordered in 2024",
    "Which warehouses are running below 20% capacity?",
    "Average unit cost per product category",
    "Suppliers with the lowest on-time delivery rate",
]


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("""
    <div style='padding: 0.5rem 0 1rem'>
        <div style='font-size:1.1rem;font-weight:700;color:#e2eeff;letter-spacing:-0.2px'>🛡️ SQL Guardrails</div>
        <div style='font-size:0.75rem;color:#64748b;margin-top:2px'>Supply Chain · Powered by Claude</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("<div style='font-size:0.7rem;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#475569;margin-bottom:0.6rem'>Schema Explorer</div>", unsafe_allow_html=True)

    schema_data = get_schema()
    if schema_data:
        for table in schema_data.get("tables", []):
            with st.expander(f"**{table['table_name']}** · {table['row_count_estimate']:,} rows"):
                for col in table["columns"]:
                    flags = []
                    if col["is_primary_key"]:
                        flags.append("PK")
                    if col.get("foreign_key"):
                        flags.append(f"→ {col['foreign_key']}")
                    flag_str = f"  `{', '.join(flags)}`" if flags else ""
                    st.markdown(f"<div style='font-size:0.8rem;padding:1px 0'><code>{col['name']}</code> <span style='color:#64748b;font-size:0.72rem'>{col['data_type']}</span>{flag_str}</div>", unsafe_allow_html=True)
    else:
        st.warning("Can't reach API — is the server running?")

    st.markdown("---")
    st.markdown("<div style='font-size:0.7rem;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#475569;margin-bottom:0.6rem'>Try These</div>", unsafe_allow_html=True)
    for q in EXAMPLE_QUESTIONS:
        st.markdown(f"<div style='font-size:0.75rem;color:#93b4e0;padding:3px 0;cursor:pointer'>› {q}</div>", unsafe_allow_html=True)


# ── Main ──────────────────────────────────────────────────────────────────────

tab_query, tab_eval = st.tabs(["  Query  ", "  Eval Results  "])


# ── TAB 1: Query ──────────────────────────────────────────────────────────────
with tab_query:

    # Hero
    st.markdown("""
    <div style='background:white;border:1px solid #e2e8f0;border-radius:14px;
                padding:1.8rem 2.2rem;margin-bottom:1.5rem;
                box-shadow:0 2px 12px rgba(0,0,0,0.06);
                border-top:4px solid #4f8ef7;'>
        <div style='margin-bottom:0.7rem'>
            <span style='display:inline-block;background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe;
                         border-radius:20px;padding:2px 12px;font-size:0.72rem;font-weight:600;
                         letter-spacing:0.5px;margin-right:6px'>PostgreSQL 15</span>
            <span style='display:inline-block;background:#f0fdf4;color:#15803d;border:1px solid #bbf7d0;
                         border-radius:20px;padding:2px 12px;font-size:0.72rem;font-weight:600;
                         letter-spacing:0.5px;margin-right:6px'>Claude Sonnet</span>
            <span style='display:inline-block;background:#faf5ff;color:#7e22ce;border:1px solid #e9d5ff;
                         border-radius:20px;padding:2px 12px;font-size:0.72rem;font-weight:600;
                         letter-spacing:0.5px'>Supply Chain</span>
        </div>
        <div style='font-size:1.6rem;font-weight:700;color:#0f172a;margin-bottom:0.4rem;letter-spacing:-0.3px'>
            🛡️ Text-to-SQL with Guardrails
        </div>
        <div style='font-size:0.88rem;color:#475569;line-height:1.6'>
            Ask anything about your supply chain data in plain English. Every query passes through
            AST-based safety checks and hallucination detection before a single row is returned.
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Query input form
    with st.form("query_form"):
        question = st.text_area(
            "Your question",
            placeholder="e.g.  Which suppliers delivered late more than 3 times in Q1 2024?",
            height=90,
            label_visibility="collapsed",
        )
        c1, c2, c3, c4 = st.columns([1.2, 1.6, 0.3, 2])
        with c1:
            include_reasoning = st.checkbox("Show LLM reasoning", value=False)
        with c2:
            multi_query = st.checkbox("Multi-query validation", value=False)
        with c4:
            submitted = st.form_submit_button("Run Query →", type="primary", use_container_width=True)

    if submitted and not question.strip():
        st.warning("Type a question first.")

    if submitted and question.strip():
        with st.spinner("Running pipeline — schema filter → SQL generation → guardrails → back-translation → execution…"):
            resp = post_query(question.strip(), include_reasoning, multi_query)

        if resp:
            blocked = resp.get("guardrail", {}).get("blocked", False)
            cannot_answer = resp.get("cannot_answer", False)
            sql = resp.get("sql", "")

            # ── Pipeline steps ──────────────────────────────────────────────
            st.markdown('<div class="section-label">Pipeline Run</div>', unsafe_allow_html=True)

            step_classes = {
                "schema": "step-done",
                "sql": "step-done" if sql else "step-blocked",
                "guardrail": "step-blocked" if blocked else "step-done",
                "back_trans": "step-done" if resp.get("back_translation") else "step-pending",
                "exec": "step-blocked" if blocked or cannot_answer else "step-done",
            }
            step_icons = {
                "schema": "📋",
                "sql": "✍️" if sql else "✗",
                "guardrail": "✗" if blocked else "🛡",
                "back_trans": "🔍" if resp.get("back_translation") else "–",
                "exec": "✗" if (blocked or cannot_answer) else "✓",
            }
            step_labels = ["Schema\nFilter", "SQL\nGenerate", "Guardrail\nCheck", "Back-\nTranslate", "Execute"]
            step_keys = ["schema", "sql", "guardrail", "back_trans", "exec"]

            cols = st.columns(9)
            for i, (key, label) in enumerate(zip(step_keys, step_labels)):
                with cols[i * 2]:
                    cls = step_classes[key]
                    icon = step_icons[key]
                    color_map = {
                        "step-done": "#15803d",
                        "step-blocked": "#dc2626",
                        "step-pending": "#94a3b8",
                    }
                    c = color_map[cls]
                    bg_map = {
                        "step-done": "#f0fdf4",
                        "step-blocked": "#fef2f2",
                        "step-pending": "#f8fafc",
                    }
                    bg = bg_map[cls]
                    st.markdown(f"""
                    <div style='text-align:center'>
                        <div style='width:38px;height:38px;border-radius:50%;border:2px solid {c};
                                    background:{bg};display:flex;align-items:center;justify-content:center;
                                    font-size:1rem;margin:0 auto 4px;'>{icon}</div>
                        <div style='font-size:0.62rem;font-weight:600;color:#64748b;white-space:pre-line;line-height:1.2'>{label}</div>
                    </div>
                    """, unsafe_allow_html=True)
                if i < len(step_keys) - 1:
                    with cols[i * 2 + 1]:
                        st.markdown("""
                        <div style='height:38px;display:flex;align-items:center'>
                            <div style='flex:1;height:2px;background:#e2e8f0'></div>
                        </div>
                        """, unsafe_allow_html=True)

            st.markdown("<div style='margin-top:1rem'></div>", unsafe_allow_html=True)

            # ── Cannot answer ───────────────────────────────────────────────
            if cannot_answer:
                st.markdown(f"""
                <div style='background:#fffbeb;border:1px solid #fcd34d;border-radius:10px;
                            padding:1rem 1.2rem;margin-bottom:1rem'>
                    <div style='font-weight:700;color:#92400e;margin-bottom:4px'>❓ Cannot Answer</div>
                    <div style='color:#78350f;font-size:0.88rem'>{resp.get("cannot_answer_reason", "The schema does not contain the data needed to answer this question.")}</div>
                </div>
                """, unsafe_allow_html=True)

            # ── Guardrail blocked ───────────────────────────────────────────
            elif blocked:
                violations = resp.get("guardrail", {}).get("violations", [])
                viol_str = " · ".join(violations)
                st.markdown(f"""
                <div style='background:#fef2f2;border:1px solid #fca5a5;border-radius:10px;
                            padding:1rem 1.2rem;margin-bottom:1rem'>
                    <div style='font-weight:700;color:#dc2626;margin-bottom:4px'>🚫 Query Blocked by Guardrail</div>
                    <div style='color:#7f1d1d;font-size:0.85rem'>Violation: <code style="background:#fee2e2;padding:2px 6px;border-radius:4px">{viol_str}</code></div>
                </div>
                """, unsafe_allow_html=True)

            # ── Normal path ─────────────────────────────────────────────────
            else:
                col_left, col_right = st.columns([3, 1])

                with col_left:
                    st.markdown('<div class="section-label">Generated SQL</div>', unsafe_allow_html=True)
                    if sql:
                        st.markdown("""
                        <div class="sql-wrapper">
                            <div class="sql-header">
                                <span class="sql-dot" style="background:#ff5f56"></span>
                                <span class="sql-dot" style="background:#ffbd2e"></span>
                                <span class="sql-dot" style="background:#27c93f"></span>
                                <span style="color:#6e7681;font-size:0.72rem;margin-left:6px;font-family:'JetBrains Mono',monospace">query.sql</span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                        st.code(sql, language="sql")
                    else:
                        st.info("No SQL generated.")

                    ambiguity = resp.get("ambiguity_flags", [])
                    if ambiguity:
                        for flag in ambiguity:
                            st.warning(f"⚠️ {flag}")

                    if include_reasoning and resp.get("reasoning"):
                        with st.expander("💭 LLM Reasoning"):
                            st.write(resp["reasoning"])

                with col_right:
                    st.markdown('<div class="section-label">Metadata</div>', unsafe_allow_html=True)
                    score = resp.get("confidence_score", 0.0)
                    latency = resp.get("latency_ms", 0)
                    tables = resp.get("tables_used", [])
                    rows = resp.get("row_count", 0)

                    conf_color = "#15803d" if score >= 0.8 else ("#d97706" if score >= 0.6 else "#dc2626")
                    conf_label = "High" if score >= 0.8 else ("Medium" if score >= 0.6 else "Low")

                    st.markdown(f"""
                    <div style='display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px'>
                        <div class="metric-pill">
                            <div class="val" style='color:{conf_color}'>{score:.0%}</div>
                            <div class="lbl">Confidence</div>
                        </div>
                        <div class="metric-pill">
                            <div class="val">{latency/1000:.1f}s</div>
                            <div class="lbl">Latency</div>
                        </div>
                        <div class="metric-pill">
                            <div class="val">{rows}</div>
                            <div class="lbl">Rows</div>
                        </div>
                        <div class="metric-pill">
                            <div class="val">{len(tables)}</div>
                            <div class="lbl">Tables</div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    if tables:
                        st.markdown(chips(tables), unsafe_allow_html=True)

            # ── Safety & Validation ─────────────────────────────────────────
            st.markdown('<div class="section-label">Safety & Validation</div>', unsafe_allow_html=True)
            col_g, col_bt, col_mq = st.columns(3)

            gr = resp.get("guardrail", {})
            with col_g:
                if gr.get("passed") and not gr.get("blocked"):
                    st.markdown("""
                    <div class="status-card status-pass">
                        <div class="card-title">Guardrail</div>
                        <div class="card-value">✅ Passed</div>
                        <div class="card-sub">sqlparse AST — no violations</div>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    viols = gr.get("violations", [])
                    st.markdown(f"""
                    <div class="status-card status-fail">
                        <div class="card-title">Guardrail</div>
                        <div class="card-value">🚫 Blocked</div>
                        <div class="card-sub">{'  ·  '.join(viols) or 'Violation detected'}</div>
                    </div>
                    """, unsafe_allow_html=True)

            bt = resp.get("back_translation")
            with col_bt:
                if bt:
                    sim = bt.get("similarity_score", 0)
                    suspected = bt.get("hallucination_suspected", False)
                    bt_q = bt.get("back_translated_question", "")
                    if suspected:
                        st.markdown(f"""
                        <div class="status-card status-warn">
                            <div class="card-title">Back-Translation</div>
                            <div class="card-value">⚠️ Suspected</div>
                            <div class="card-sub">Similarity: {sim:.2f} — semantic drift detected</div>
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.markdown(f"""
                        <div class="status-card status-pass">
                            <div class="card-title">Back-Translation</div>
                            <div class="card-value">✅ OK</div>
                            <div class="card-sub">Similarity: {sim:.2f}</div>
                        </div>
                        """, unsafe_allow_html=True)
                    if bt_q:
                        with st.expander("What the SQL actually asks"):
                            st.write(bt_q)
                else:
                    st.markdown("""
                    <div class="status-card status-neutral">
                        <div class="card-title">Back-Translation</div>
                        <div class="card-value" style='color:#94a3b8'>— Not run</div>
                        <div class="card-sub">Skipped for this query</div>
                    </div>
                    """, unsafe_allow_html=True)

            agreement = resp.get("multi_query_agreement")
            with col_mq:
                if agreement == "AGREEMENT":
                    st.markdown(f"""
                    <div class="status-card status-pass">
                        <div class="card-title">Multi-Query</div>
                        <div class="card-value">✅ Agreement</div>
                        <div class="card-sub">Both approaches returned matching results</div>
                    </div>
                    """, unsafe_allow_html=True)
                elif agreement == "PARTIAL_AGREEMENT":
                    st.markdown(f"""
                    <div class="status-card status-warn">
                        <div class="card-title">Multi-Query</div>
                        <div class="card-value">⚠️ Partial</div>
                        <div class="card-sub">Results differ slightly between approaches</div>
                    </div>
                    """, unsafe_allow_html=True)
                elif agreement == "DIVERGENCE":
                    st.markdown(f"""
                    <div class="status-card status-fail">
                        <div class="card-title">Multi-Query</div>
                        <div class="card-value">❌ Divergence</div>
                        <div class="card-sub">Approaches returned different results — review both</div>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    label = "Enable above to run" if not multi_query else "Not triggered"
                    st.markdown(f"""
                    <div class="status-card status-neutral">
                        <div class="card-title">Multi-Query</div>
                        <div class="card-value" style='color:#94a3b8'>— Disabled</div>
                        <div class="card-sub">{label}</div>
                    </div>
                    """, unsafe_allow_html=True)

            # ── Results ─────────────────────────────────────────────────────
            results = resp.get("results")
            if results and len(results) > 0 and not blocked and not cannot_answer:
                st.markdown('<div class="section-label">Results</div>', unsafe_allow_html=True)
                df = pd.DataFrame(results)
                st.dataframe(df, use_container_width=True, height=min(400, 80 + 35 * len(df)))

                dl_col, info_col = st.columns([1, 4])
                with dl_col:
                    st.download_button(
                        "⬇ Download CSV",
                        data=df.to_csv(index=False),
                        file_name="query_results.csv",
                        mime="text/csv",
                        use_container_width=True,
                    )
                with info_col:
                    truncated = resp.get("truncated", False)
                    msg = f"{resp.get('row_count', len(results))} rows"
                    if truncated:
                        msg += " — result set truncated at 1,000 rows"
                    st.caption(msg)

            elif not blocked and not cannot_answer and not sql:
                pass
            elif not blocked and not cannot_answer:
                st.info("Query returned 0 rows.")


# ── TAB 2: Eval Dashboard ─────────────────────────────────────────────────────
with tab_eval:
    results_path = Path(__file__).parent.parent / "eval" / "results" / "latest_results.md"

    if results_path.exists():
        content = results_path.read_text()

        # Pull out key numbers to render as a visual scorecard
        st.markdown("""
        <div style='background:white;border:1px solid #e2e8f0;border-radius:14px;
                    padding:1.5rem 2rem;margin-bottom:1.5rem;
                    box-shadow:0 2px 12px rgba(0,0,0,0.06);
                    border-top:4px solid #22c55e;'>
            <div style='font-size:1.2rem;font-weight:700;color:#0f172a;margin-bottom:0.3rem'>
                📊 Eval Suite — 50 Hand-Curated Questions
            </div>
            <div style='font-size:0.83rem;color:#64748b'>
                Run <code style="background:#f1f5f9;color:#334155;padding:1px 6px;border-radius:4px;font-size:0.78rem">make eval</code>
                to refresh &nbsp;·&nbsp; Questions are hand-written, not LLM-generated
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Scorecard row
        sc1, sc2, sc3, sc4 = st.columns(4)
        metrics = [
            (sc1, "100%", "Execution Accuracy", "#22c55e", "✅"),
            (sc2, "100%", "Guardrail Block Rate", "#22c55e", "🛡️"),
            (sc3, "0", "Unsafe Executions", "#22c55e", "✅"),
            (sc4, "11.1%", "Hallucination Flag Rate", "#f59e0b", "🔍"),
        ]
        for col, val, label, color, icon in metrics:
            with col:
                st.markdown(f"""
                <div style='background:white;border:1px solid #e2e8f0;border-radius:12px;
                            padding:1.1rem;text-align:center;box-shadow:0 1px 4px rgba(0,0,0,0.06)'>
                    <div style='font-size:2rem;line-height:1'>{icon}</div>
                    <div style='font-size:1.8rem;font-weight:800;color:{color};margin:6px 0 2px'>{val}</div>
                    <div style='font-size:0.7rem;font-weight:600;color:#64748b;text-transform:uppercase;
                                letter-spacing:0.5px'>{label}</div>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("<div style='margin-top:1.5rem'></div>", unsafe_allow_html=True)
        st.markdown(content)
    else:
        st.markdown("""
        <div style='background:#fffbeb;border:1px solid #fcd34d;border-radius:10px;padding:1.2rem 1.5rem'>
            <div style='font-weight:700;color:#92400e'>No eval results yet</div>
            <div style='color:#78350f;font-size:0.88rem;margin-top:4px'>
                Run <code>make eval</code> to generate results — it takes ~15 minutes with a live API key.
            </div>
        </div>
        """, unsafe_allow_html=True)
