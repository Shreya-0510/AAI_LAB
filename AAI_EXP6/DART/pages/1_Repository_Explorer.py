from pathlib import Path
import sys
import streamlit as st
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "src"))
from dart.mcp_client.connection import call_mcp_tool
import asyncio
st.set_page_config(page_title="Repository Explorer | DART", layout="wide")
st.title("Repository Explorer")
st.caption("Inspect a local Python repository through dynamically discovered MCP tools.")
repo = st.text_input("Repository path", value=str((ROOT / "sample_data" / "demo_repository").resolve()))
if st.button("Inspect repository", type="primary"):
    try:
        data = asyncio.run(call_mcp_tool("inspect_repository", {"repository": str(Path(repo).expanduser().resolve())}))
        a,b,c = st.columns(3); a.metric("Python files", data.get("python_file_count", 0)); b.metric("Test files", len(data.get("test_files", []))); c.metric("Commit", str(data.get("commit_hash", "unknown"))[:12])
        st.subheader("Python files"); st.dataframe(data.get("python_files", []), use_container_width=True)
        st.subheader("Test files"); st.dataframe(data.get("test_files", []), use_container_width=True)
    except Exception as exc: st.error(str(exc))
