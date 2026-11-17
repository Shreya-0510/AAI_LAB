from __future__ import annotations
from dart.analysis.selection_strategies import validate_test_paths

def validate_plan(plan: dict, discovered_tests: list[str]) -> dict:
    selected = plan.get("selected_tests", [])
    if not isinstance(selected, list): selected = []
    valid, rejected = validate_test_paths([str(x) for x in selected], discovered_tests)
    confidence = plan.get("confidence", 0.5)
    try: confidence = min(1.0, max(0.0, float(confidence)))
    except (TypeError, ValueError): confidence = 0.5
    return {"valid": bool(valid) and not rejected, "selected_tests": valid, "rejected_tests": rejected, "confidence": confidence, "rationale": str(plan.get("rationale", "")), "evidence_files": plan.get("evidence_files", [])}
