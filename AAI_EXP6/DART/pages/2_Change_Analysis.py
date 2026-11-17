from pathlib import Path
import sys, asyncio
import streamlit as st
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "src"))
from dart.mcp_client.connection import call_mcp_tool
st.set_page_config(page_title="Change Analysis | DART", layout="wide")
st.title("Change Impact Analysis")
repo = st.text_input("Repository path", value=str((ROOT / "sample_data" / "demo_repository").resolve()))
base = st.text_input("Base commit / ref (optional)", value="")
head = st.text_input("Head ref", value="HEAD")
if st.button("Analyze changes", type="primary"):
    try:
        r = asyncio.run(call_mcp_tool("get_changed_files", {"repository": str(Path(repo).resolve()), "base_ref": base or None, "head_ref": head or "HEAD"}))
        st.metric("Changed files", len(r.get("changed_files", []))); st.dataframe(r.get("changed_files", []), use_container_width=True)
        st.subheader("Diff"); st.code(r.get("diff_text", "No diff available."), language="diff")
    except Exception as exc: st.error(str(exc))
