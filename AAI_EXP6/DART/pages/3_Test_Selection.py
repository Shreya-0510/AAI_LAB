from pathlib import Path
import sys, asyncio
import streamlit as st
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "src"))
from dart.mcp_client.connection import call_mcp_tool
st.set_page_config(page_title="Test Selection | DART", layout="wide")
st.title("Test Selection and Validation")
repo = st.text_input("Repository path", value=str((ROOT / "sample_data" / "demo_repository").resolve()))
changed = st.text_area("Changed files (one path per line)", value="src/calculator.py")
if st.button("Map and validate tests", type="primary"):
    try:
        root = str(Path(repo).resolve()); changed_files = [x.strip() for x in changed.splitlines() if x.strip()]
        mapping = asyncio.run(call_mcp_tool("map_tests_to_modules", {"repository": root, "changed_files": changed_files}))
        st.subheader("Suggested tests"); st.dataframe(mapping.get("selected_tests", []), use_container_width=True)
        st.subheader("Module-to-test mapping"); st.json(mapping.get("mapping", {}))
        validation = asyncio.run(call_mcp_tool("validate_test_plan", {"repository": root, "selected_tests": mapping.get("selected_tests", [])}))
        st.subheader("Supervisor validation"); st.json(validation)
    except Exception as exc: st.error(str(exc))
