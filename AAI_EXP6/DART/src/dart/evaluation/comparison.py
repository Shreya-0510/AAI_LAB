from __future__ import annotations
import pandas as pd

def compare_runs(records: list[dict]) -> pd.DataFrame:
    rows = []
    for record in records:
        metrics = record.get("metrics", {})
        rows.append({"strategy": record.get("strategy"), "duration_seconds": metrics.get("duration_seconds"), "end_to_end_seconds": metrics.get("end_to_end_seconds"), "selected_test_count": metrics.get("selected_test_count"), "total_test_count": metrics.get("total_test_count"), "test_reduction_pct": metrics.get("test_reduction_pct"), "failed": metrics.get("failed"), "workflow_success": metrics.get("workflow_success")})
    return pd.DataFrame(rows)
