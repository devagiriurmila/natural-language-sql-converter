"""Streamlit user interface. Run with:  streamlit run app.py"""
from __future__ import annotations

import time

import pandas as pd
import streamlit as st

import evaluator
from config import FOREIGN_KEYS, SCHEMA, load_settings
from database import execute_validated, init_database, table_preview
from prompt_templates import STRATEGIES, STRATEGY_LABELS, build_system_prompt
from sql_generator import GenerationResult, generate_sql
from sql_validator import ValidationResult, validate_sql

SAMPLE_QUESTIONS = [
    "Show all students from CSE.",
    "Find students who scored above 80 marks.",
    "Show the top five students by marks.",
    "Calculate the average marks of each department.",
    "Count students in each department.",
    "Find departments whose average marks exceed 75.",
    "Show students enrolled in Python.",
    "Find the student with the highest marks.",
    "Count enrollments in each course.",
    "Show students enrolled in Database Systems during semester 2.",
]

st.set_page_config(page_title="Natural Language-to-SQL Generator", page_icon="🗄️", layout="wide")
settings = load_settings()
init_database(settings.db_path)  # creates data/students.db on first run

for key, default in {"question": "", "generation": None, "validation": None, "result": None,
                     "history": [], "comparison": None, "last_error": ""}.items():
    st.session_state.setdefault(key, default)


def use_sample() -> None:
    st.session_state.question = st.session_state.sample_choice
    reset_outputs()


def reset_outputs() -> None:
    st.session_state.generation = st.session_state.validation = None
    st.session_state.result = st.session_state.comparison = None
    st.session_state.last_error = ""


def do_generate(strategy: str) -> None:
    with st.spinner("Asking the language model..."):
        gen = generate_sql(st.session_state.question, strategy, settings)
    st.session_state.generation, st.session_state.result = gen, None
    # Validation is separate from, and always happens before, execution.
    st.session_state.validation = validate_sql(gen.sql, settings.max_rows) if gen.ok else None


# ---------------------------------------------------------------- sidebar ----
with st.sidebar:
    st.header("📘 Project")
    st.write("**24CS2022 – Prompt Engineering**  \nNatural Language-to-SQL Generator")
    st.subheader("Model configuration")
    if settings.api_configured:
        st.success(f"API key found · model: `{settings.model}`")
    else:
        st.warning("No API key configured. Schema, validator and offline checks still work.")
    st.caption(f"Temperature: {settings.temperature if settings.temperature is not None else 'default'} · "
               f"max rows: {settings.max_rows}")
    st.subheader("Prompt strategy")
    strategy = st.radio("Strategy", STRATEGIES, format_func=STRATEGY_LABELS.get, label_visibility="collapsed")
    st.subheader("Schema overview")
    for table, cols in SCHEMA.items():
        st.markdown(f"**{table}**: " + ", ".join(f"`{c}`" for c in cols))
    st.subheader("Sample questions")
    for q in SAMPLE_QUESTIONS[:5]:
        st.caption("• " + q)
    if st.button("Clear everything", width="stretch"):
        for k in ("question", "history"):
            st.session_state[k] = "" if k == "question" else []
        reset_outputs()
        st.rerun()

# ------------------------------------------------------------------ header ----
st.title("Natural Language-to-SQL Generator")
st.caption("Ask questions in English. Generate, validate, and execute SQL using prompt engineering.")
tab_work, tab_schema, tab_prompts, tab_eval, tab_hist = st.tabs(
    ["Workspace", "Database schema", "Prompt comparison", "Evaluation", "Query history"])

# --------------------------------------------------------------- workspace ----
with tab_work:
    if not settings.api_configured:
        st.info("**API key missing.** Copy `.env.example` to `.env`, set `OPENAI_API_KEY`, then restart "
                "the app. Until then you can browse the schema and run the offline evaluation.")
    c1, c2 = st.columns([3, 1])
    c1.selectbox("Example questions", SAMPLE_QUESTIONS, key="sample_choice")
    c2.button("Use example", on_click=use_sample, width="stretch")
    st.text_area("Your question", key="question", height=90, max_chars=500,
                 placeholder="e.g. Which department has the highest average marks?")
    if st.button("Generate SQL", type="primary"):
        do_generate(strategy)

    gen: GenerationResult | None = st.session_state.generation
    val: ValidationResult | None = st.session_state.validation
    if gen is not None:
        if gen.status == "error":
            st.error(gen.message)
        elif gen.status in {"clarification_needed", "unsupported"}:
            st.warning(f"No SQL generated ({gen.status.replace('_', ' ')}): {gen.message or 'please rephrase.'}")
        else:
            st.subheader("Generated SQL")
            st.code(val.sql if val and val.is_valid else gen.sql, language="sql")
            st.caption(f"Strategy: {STRATEGY_LABELS[gen.strategy]} · model: {gen.model} · {gen.elapsed:.2f}s")
            if val and val.is_valid:
                st.success("✅ Validation passed")
                for w in val.warnings:
                    st.caption("ℹ️ " + w)
            elif val:
                st.error("❌ Validation failed – this query will NOT be executed.")
                for e in val.errors:
                    st.write("• " + e)
                st.caption("Tip: rephrase the question or try another prompt strategy.")
            if gen.explanation:
                st.markdown(f"**Explanation:** {gen.explanation}")
            if st.button("Execute query", disabled=not (val and val.is_valid)):
                res = execute_validated(val, settings.db_path, settings.max_rows, settings.query_timeout)
                st.session_state.result = res
                st.session_state.history.append({
                    "time": time.strftime("%H:%M:%S"), "question": st.session_state.question,
                    "strategy": STRATEGY_LABELS[gen.strategy], "sql": val.sql,
                    "rows": len(res.data) if res.ok else None, "status": "ok" if res.ok else "failed"})
    res = st.session_state.result
    if res is not None:
        if res.ok:
            st.subheader("Results")
            st.dataframe(res.data, width="stretch", hide_index=True)
            note = " (truncated to the row limit)" if res.truncated else ""
            st.caption(f"{len(res.data)} row(s){note} · {res.elapsed * 1000:.0f} ms")
        else:
            st.error(res.error)

# ------------------------------------------------------------------ schema ----
with tab_schema:
    st.subheader("Tables and relationships")
    for table, cols in SCHEMA.items():
        with st.expander(f"{table}", expanded=True):
            st.table(pd.DataFrame([(c, t, d) for c, (t, d) in cols.items()], columns=["Column", "Type", "Description"]))
            st.dataframe(table_preview(table, settings.db_path), width="stretch", hide_index=True)
    st.markdown("**Foreign keys:** " + "; ".join(f"`{a}.{b}` → `{c}.{d}`" for a, b, c, d in FOREIGN_KEYS))

# ------------------------------------------------------- prompt comparison ----
with tab_prompts:
    st.subheader("Prompt comparison")
    st.write("All three strategies share the same task, schema facts, safety rules and output format. "
             "Only the extra guidance differs.")
    rows = [{"Strategy": STRATEGY_LABELS[s], "Prompt characters": len(build_system_prompt(s)),
             "≈ tokens (chars/4, rough)": len(build_system_prompt(s)) // 4} for s in STRATEGIES]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    for s in STRATEGIES:
        with st.expander(f"View system prompt: {STRATEGY_LABELS[s]}"):
            st.code(build_system_prompt(s), language="text")
    st.markdown("**Run all strategies on your current question** (makes 3 API calls)")
    if st.button("Compare strategies", disabled=not settings.api_configured):
        out = []
        with st.spinner("Calling the model three times..."):
            for s in STRATEGIES:
                g = generate_sql(st.session_state.question, s, settings)
                v = validate_sql(g.sql, settings.max_rows) if g.ok else None
                out.append({"Strategy": STRATEGY_LABELS[s], "Status": g.status,
                            "SQL": (v.sql if v and v.is_valid else g.sql) or g.message,
                            "Valid": bool(v and v.is_valid), "Seconds": round(g.elapsed, 2)})
        st.session_state.comparison = pd.DataFrame(out)
    if st.session_state.comparison is not None:
        st.dataframe(st.session_state.comparison, hide_index=True, width="stretch")

# -------------------------------------------------------------- evaluation ----
with tab_eval:
    st.subheader("Evaluation metrics")
    st.caption(f"Benchmark: {len(evaluator.BENCHMARK)} fixed questions "
               f"({sum(1 for b in evaluator.BENCHMARK if b['reference_sql'])} answerable + "
               f"{sum(1 for b in evaluator.BENCHMARK if not b['reference_sql'])} that must be refused).")
    with st.expander("Metric definitions"):
        st.text(evaluator.__doc__.split("METRIC DEFINITIONS")[1])
    o1, o2 = st.columns(2)
    if o1.button("Run offline pipeline check (no API)"):
        summ, _ = evaluator.run_offline_check(settings.db_path)
        st.warning("OFFLINE PIPELINE CHECK – reference SQL is used as a stand-in model. "
                   "This verifies the code, NOT the LLM.")
        st.dataframe(summ, hide_index=True, width="stretch")
    n = o2.slider("Live evaluation: number of questions", 5, len(evaluator.BENCHMARK), 10)
    if o2.button("Run LIVE evaluation (uses API credits)", disabled=not settings.api_configured):
        bar = st.progress(0.0)
        summ, det = evaluator.run_evaluation(evaluator.live_generator, limit=n, mode="live",
                                             progress=lambda d, t: bar.progress(d / t))
        evaluator.save_results(det)
        st.success("Live results saved to data/evaluation_results.csv")
    if not settings.api_configured:
        st.info("Live evaluation needs an API key. No results are shown until real experiments are run.")
    saved = evaluator.load_saved_results()
    if saved is not None and not saved.empty:
        live = saved[saved["mode"] == "live"] if "mode" in saved else saved
        if not live.empty:
            summary = evaluator.summarise(live.assign(
                valid_sql=live["valid_sql"].astype(bool), execution_match=live["execution_match"].astype(bool),
                exact_match=live["exact_match"].astype(bool), technical_error=live["technical_error"].astype(bool),
                behavior_correct=live["behavior_correct"].astype(bool)))
            st.markdown("**Saved live results**")
            st.dataframe(summary, hide_index=True, width="stretch")
            st.bar_chart(summary.set_index("Strategy")[["Valid SQL rate (%)", "Execution accuracy (%)", "Exact SQL match (%)"]])

# ----------------------------------------------------------------- history ----
with tab_hist:
    st.subheader("Query history (this session)")
    if st.session_state.history:
        st.dataframe(pd.DataFrame(st.session_state.history), hide_index=True, width="stretch")
        if st.button("Clear history"):
            st.session_state.history = []
            st.rerun()
    else:
        st.write("No queries executed yet.")
