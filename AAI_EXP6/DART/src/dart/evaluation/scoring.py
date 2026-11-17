from __future__ import annotations

def calculate_run_metrics(total_test_count: int, selected_test_count: int, execution: dict, end_to_end_seconds: float) -> dict:
    reduction = 0.0 if total_test_count <= 0 else max(0.0, (total_test_count - selected_test_count) / total_test_count * 100)
    return {"total_test_count": total_test_count, "selected_test_count": selected_test_count, "test_reduction_pct": round(reduction, 2), "duration_seconds": round(float(execution.get("duration_seconds", 0.0)), 4), "end_to_end_seconds": round(end_to_end_seconds, 4), "passed": int(execution.get("passed", 0) or 0), "failed": int(execution.get("failed", 0) or 0), "errors": int(execution.get("errors", 0) or 0), "skipped": int(execution.get("skipped", 0) or 0), "return_code": execution.get("return_code"), "workflow_success": execution.get("status") == "passed"}

def selection_scores(selected: set[str], expected_relevant: set[str]) -> dict:
    """Compute selection precision/recall against externally curated relevant test paths."""
    tp = len(selected & expected_relevant)
    precision = tp / len(selected) if selected else 0.0
    recall = tp / len(expected_relevant) if expected_relevant else 0.0
    return {"true_positive_selection": tp, "selection_precision": precision, "selection_recall": recall, "ground_truth_size": len(expected_relevant), "note": "Requires curated expected-relevant-test ground truth."}

def regression_detection_rate(detected_faults: set[str], injected_faults: set[str]) -> dict:
    detected = len(detected_faults & injected_faults)
    return {"detected_fault_count": detected, "fault_count": len(injected_faults), "regression_detection_rate": detected / len(injected_faults) if injected_faults else None, "note": "Requires controlled faults and known detection outcomes."}
