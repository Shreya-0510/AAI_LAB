from pathlib import Path
import sys
import pandas as pd
import plotly.express as px
import streamlit as st
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "src"))
from dart.config import get_settings
st.set_page_config(page_title="Experiment Results | DART", layout="wide")
st.title("Experimental Results")
st.caption("Review repeated runs. Use multiple repositories and controlled fault scenarios before making effectiveness claims.")
csv_path = get_settings().artifacts_dir / "runs_summary.csv"
if not csv_path.exists(): st.info("No results yet. Run one or more strategies from the main dashboard.")
else:
    try:
        df = pd.read_csv(csv_path)
        st.dataframe(df, use_container_width=True, hide_index=True)
        if "strategy" in df and "duration_seconds" in df:
            st.plotly_chart(px.box(df, x="strategy", y="duration_seconds", title="Execution-time variability by strategy"), use_container_width=True)
        st.download_button("Download summary CSV", df.to_csv(index=False), file_name="dart_runs_summary.csv", mime="text/csv")
    except Exception as exc: st.error(f"Could not load summary: {exc}")
