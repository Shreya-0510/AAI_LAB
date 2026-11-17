from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import time
import uuid

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from dart.config import get_settings  # noqa: E402
from dart.mcp_client.connection import call_mcp_tool, list_mcp_tools  # noqa: E402
from dart.orchestration.supervisor import analyze_repository_workflow, execute_strategy_workflow  # noqa: E402
from dart.reporting.report_builder import save_run_report  # noqa: E402

settings = get_settings()
st.set_page_config(page_title="DART | Regression Testing", page_icon="🧪", layout="wide")
st.markdown("""
<style>
:root { color-scheme: light; }
.block-container { padding-top: 1.7rem; padding-bottom: 2rem; max-width: 1500px; }
[data-testid="stAppViewContainer"] { background: #f7f9fc; }
[data-testid="stSidebar"] { background: #ffffff; border-right: 1px solid #e5eaf1; }
.dart-hero { background: #ffffff; border: 1px solid #e3e9f2; border-radius: 16px; padding: 22px 26px; }
.dart-kicker { color: #2563eb; font-weight: 700; letter-spacing: .12em; font-size: .75rem; }
.dart-subtitle { color: #536174; margin-top: .25rem; }
[data-testid="stMetric"] { background: #fff; border: 1px solid #e3e9f2; border-radius: 12px; padding: 14px; }
div[data-testid="stButton"] > button { border-radius: 9px; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

if "analysis" not in st.session_state:
    st.session_state.analysis = None
if "runs" not in st.session_state:
    st.session_state.runs = []

with st.sidebar:
    st.markdown("## DART")
    st.caption("Dependency-Aware Regression Testing")
    st.divider()
    repo_text = st.text_input("Local Python repository", value=str(Path(settings.repository_root).resolve()))
    base_ref = st.text_input("Base ref (optional)", value="")
    head_ref = st.text_input("Head ref (optional)", value="HEAD")
    timeout = st.number_input("Test timeout (seconds)", min_value=10, max_value=900, value=settings.test_timeout_seconds, step=10)
    st.caption("Test execution runs repository code. Use only trusted repositories.")
    st.divider()
    st.caption("LLM status")
    if settings.groq_api_key:
        st.success(f"Groq configured · {settings.groq_model}")
    else:
        st.warning("No Groq key · heuristic planner mode")

st.markdown('<div class="dart-hero"><div class="dart-kicker">CHANGE INTELLIGENCE / REGRESSION TESTING</div><h1 style="margin:.35rem 0 0 0; color:#14213d;">DART</h1><div class="dart-subtitle">Dependency-Aware Regression Testing</div><p style="margin:.9rem 0 0 0; color:#536174;">Analyze code changes, map affected tests, and compare full-suite, LLM-only, and hybrid test-selection strategies.</p></div>', unsafe_allow_html=True)
st.write("")

col_a, col_b = st.columns([1.2, 1])
with col_a:
    st.subheader("1. Repository analysis")
    if st.button("Analyze repository via MCP", type="primary", use_container_width=True):
        repo = Path(repo_text).expanduser().resolve()
        if not repo.exists() or not repo.is_dir():
            st.error("Enter an existing local directory.")
        else:
            with st.spinner("Connecting to MCP server and analyzing repository…"):
                try:
                    st.session_state.analysis = asyncio.run(analyze_repository_workflow(str(repo), base_ref.strip() or None, head_ref.strip() or None))
                    st.session_state.repo = str(repo)
                except Exception as exc:
                    st.error(f"Analysis failed: {exc}")
with col_b:
    st.subheader("MCP tool discovery")
    if st.button("Discover server tools", use_container_width=True):
        try:
            tools = asyncio.run(list_mcp_tools())
            st.session_state.mcp_tools = tools
        except Exception as exc:
            st.error(f"Could not start MCP server: {exc}")
    if st.session_state.get("mcp_tools"):
        st.caption(f"Discovered {len(st.session_state.mcp_tools)} tools at runtime")
        st.dataframe(pd.DataFrame(st.session_state.mcp_tools), use_container_width=True, hide_index=True)

analysis = st.session_state.analysis
if analysis:
    st.divider()
    st.subheader("Repository snapshot")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Python files", analysis.get("python_file_count", 0))
    m2.metric("Test files", len(analysis.get("test_files", [])))
    m3.metric("Changed files", len(analysis.get("changed_files", [])))
    m4.metric("Dependency edges", analysis.get("dependency_edge_count", 0))
    if analysis.get("mcp_status") == "connected":
        st.success("MCP connected. Repository analysis was completed by the MCP server.")
    tabs = st.tabs(["Changed files", "Dependency graph", "Discovered tests", "Planner output"])
    with tabs[0]:
        st.dataframe(pd.DataFrame({"Changed file": analysis.get("changed_files", [])}), use_container_width=True, hide_index=True)
        if analysis.get("diff_text"):
            with st.expander("View diff (truncated if large)"):
                st.code(analysis["diff_text"][:20000], language="diff")
    with tabs[1]:
        edges = analysis.get("dependency_edges", [])
        if edges:
            st.dataframe(pd.DataFrame(edges), use_container_width=True, hide_index=True)
        else:
            st.info("No internal Python import edges were found. Static analysis may not resolve dynamic imports.")
    with tabs[2]:
        st.dataframe(pd.DataFrame({"Test file": analysis.get("test_files", [])}), use_container_width=True, hide_index=True)
    with tabs[3]:
        st.write(analysis.get("planner_summary", "No planner output yet."))
        st.caption(f"Planner mode: {analysis.get('planner_mode', 'unknown')}")

    st.divider()
    st.subheader("2. Compare regression-testing strategies")
    st.warning("The next action executes tests from the selected repository. Continue only if you trust its code.")
    strategy_labels = {
        "full_suite": "A · Full-suite baseline",
        "llm_only": "B · LLM-only selection",
        "hybrid": "C · Hybrid DART",
    }
    selected = st.multiselect("Strategies to run", list(strategy_labels), default=["full_suite", "llm_only", "hybrid"], format_func=lambda x: strategy_labels[x])
    run_col, clear_col = st.columns([1, 4])
    with run_col:
        run_clicked = st.button("Run selected strategies", type="primary", disabled=not selected)
    if run_clicked:
        all_results = []
        progress = st.progress(0, text="Preparing benchmark…")
        for i, strategy in enumerate(selected):
            progress.progress(i / max(len(selected), 1), text=f"Running {strategy_labels[strategy]}…")
            try:
                result = asyncio.run(execute_strategy_workflow(
                    repository=st.session_state.repo,
                    analysis=analysis,
                    strategy=strategy,
                    timeout_seconds=int(timeout),
                ))
                all_results.append(result)
                st.session_state.runs.append(result)
            except Exception as exc:
                all_results.append({"strategy": strategy, "status": "error", "error": str(exc)})
        progress.progress(1.0, text="Runs finished")
        st.session_state.latest_results = all_results
        for result in all_results:
            save_run_report(result, settings.artifacts_dir)

    results = st.session_state.get("latest_results", [])
    if results:
        st.divider()
        st.subheader("3. Experimental results")
        rows = []
        for r in results:
            if r.get("status") == "error":
                rows.append({"Strategy": r.get("strategy"), "Status": "Error", "Selected files": "—", "Total files": "—", "Reduction": "—", "Duration (s)": "—", "Passed": "—", "Failed": "—", "Planner": "—"})
                continue
            met = r.get("metrics", {})
            rows.append({"Strategy": r.get("strategy"), "Status": r.get("status", "completed"), "Selected files": met.get("selected_test_count", 0), "Total files": met.get("total_test_count", 0), "Reduction": f"{met.get('test_reduction_pct', 0):.1f}%", "Duration (s)": round(met.get("duration_seconds", 0), 2), "Passed": met.get("passed", 0), "Failed": met.get("failed", 0), "Planner": r.get("planner_mode", "unknown")})
        frame = pd.DataFrame(rows)
        st.dataframe(frame, use_container_width=True, hide_index=True)
        good = [r for r in results if r.get("status") != "error"]
        if good:
            chart_data = pd.DataFrame([{"Strategy": r.get("strategy"), "Duration (s)": r.get("metrics", {}).get("duration_seconds", 0), "Test files selected": r.get("metrics", {}).get("selected_test_count", 0)} for r in good])
            c1, c2 = st.columns(2)
            with c1:
                st.plotly_chart(px.bar(chart_data, x="Strategy", y="Duration (s)", title="End-to-end duration", color="Strategy"), use_container_width=True)
            with c2:
                st.plotly_chart(px.bar(chart_data, x="Strategy", y="Test files selected", title="Test-file selection", color="Strategy"), use_container_width=True)
            for r in good:
                with st.expander(f"Trace · {r.get('strategy')} · {r.get('run_id', '')}"):
                    st.json({"planner_mode": r.get("planner_mode"), "plan": r.get("plan", {}), "validation": r.get("validation", {}), "policy": r.get("policy", {}), "execution": r.get("execution", {}), "trace": r.get("trace", [])})
                    if r.get("execution", {}).get("output"):
                        st.code(r["execution"]["output"][-8000:])
        st.caption("Interpret results across repeated runs and multiple repositories. Reduction in selected test files is not itself proof of preserved defect detection.")
else:
    st.info("Start by analyzing the demo repository or enter a trusted local Python repository in the sidebar.")

st.divider()
st.caption("DART research prototype · Keep repository commit hashes and benchmark scenarios with every reported result.")
