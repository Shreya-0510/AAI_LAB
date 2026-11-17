from dart.orchestration.policy import validate_execution_policy

def test_policy_rejects_unapproved_execution():
    result = validate_execution_policy(["tests/test_a.py"], ["tests/test_a.py"], approved=False)
    assert result["allowed"] is False

def test_policy_rejects_unknown_test():
    result = validate_execution_policy(["../../evil.py"], ["tests/test_a.py"], approved=True)
    assert result["allowed"] is False
    assert result["rejected_tests"]
