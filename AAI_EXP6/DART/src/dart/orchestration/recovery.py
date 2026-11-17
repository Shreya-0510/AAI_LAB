from __future__ import annotations

def classify_failure(result: dict) -> dict:
    output = str(result.get("output", "")).lower()
    if result.get("timed_out") or result.get("status") == "timeout":
        return {"recoverable": True, "category": "timeout", "suggestion": "Review timeout and test isolation; rerun only after user approval."}
    if "no module named" in output or "importerror" in output:
        return {"recoverable": False, "category": "environment", "suggestion": "Install project test dependencies in the repository environment."}
    if result.get("status") == "failed":
        return {"recoverable": False, "category": "test_failure", "suggestion": "Inspect the failure; do not automatically retry deterministic test failures."}
    if result.get("status") == "error":
        return {"recoverable": False, "category": "runner_error", "suggestion": "Inspect runner output and permissions."}
    return {"recoverable": False, "category": "unknown", "suggestion": "Inspect the trace."}
