from __future__ import annotations
from dart.analysis.selection_strategies import validate_test_paths

def validate_execution_policy(selected_tests: list[str], discovered_tests: list[str], approved: bool) -> dict:
    valid, rejected = validate_test_paths(selected_tests, discovered_tests)
    reasons = []
    if not approved: reasons.append("Explicit user approval is required before running repository tests.")
    if rejected: reasons.append("Plan includes targets outside the discovered-test allowlist.")
    if not valid: reasons.append("No approved test files remain after validation.")
    return {"allowed": bool(approved and valid and not rejected), "valid_tests": valid, "rejected_tests": rejected, "reasons": reasons, "policy_version": "1.0"}
