from pathlib import Path
import sys, json
import streamlit as st
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "src"))
from dart.config import get_settings
st.set_page_config(page_title="Execution Traces | DART", layout="wide")
st.title("Execution Traces")
st.caption("Run JSON files are saved under the configured artifacts directory.")
folder = get_settings().artifacts_dir
files = sorted(folder.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True) if folder.exists() else []
if not files: st.info("No trace artifacts yet. Run a strategy from the main dashboard first.")
else:
    selected = st.selectbox("Run artifact", files, format_func=lambda p: p.name)
    try:
        data = json.loads(selected.read_text(encoding="utf-8")); st.json({"run_id": data.get("run_id"), "strategy": data.get("strategy"), "commit_hash": data.get("commit_hash"), "trace": data.get("trace"), "validation": data.get("validation"), "policy": data.get("policy"), "recovery": data.get("recovery")})
        st.download_button("Download JSON trace", selected.read_bytes(), file_name=selected.name, mime="application/json")
    except Exception as exc: st.error(str(exc))
