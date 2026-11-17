from __future__ import annotations
from pathlib import Path


def _normalize_test_path(path: str | Path) -> str:
    normalized = Path(str(path)).as_posix()
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.lstrip("./")


def heuristic_test_selection(changed_files: list[str], test_files: list[str], source_files: list[str], dependency_edges: list[dict[str, str]]) -> list[str]:
    from dart.analysis.test_mapping import tests_for_changed_files
    selected, _ = tests_for_changed_files(changed_files, test_files, source_files, dependency_edges)
    if selected: return selected
    # Conservative fallback: if static mapping has no hits, select all discovered tests rather than none.
    return list(test_files)

def validate_test_paths(selected_tests: list[str], discovered_tests: list[str]) -> tuple[list[str], list[str]]:
    approved = {_normalize_test_path(path) for path in discovered_tests}
    valid, rejected = [], []
    for item in selected_tests:
        normalized = _normalize_test_path(item)
        if normalized in approved and normalized not in valid:
            valid.append(normalized)
        else:
            rejected.append(str(item))
    return valid, rejected
