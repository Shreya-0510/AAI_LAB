from dart.analysis.selection_strategies import validate_test_paths


def test_only_allowlisted_test_paths_are_valid():
    valid, rejected = validate_test_paths(["tests/test_a.py", "../../other.py"], ["tests/test_a.py"])
    assert valid == ["tests/test_a.py"]
    assert rejected == ["../../other.py"]


def test_normalizes_allowlisted_paths_before_validation():
    valid, rejected = validate_test_paths(["./tests/test_a.py", "tests\\test_b.py"], ["tests/test_a.py", "tests/test_b.py"])
    assert valid == ["tests/test_a.py", "tests/test_b.py"]
    assert rejected == []
