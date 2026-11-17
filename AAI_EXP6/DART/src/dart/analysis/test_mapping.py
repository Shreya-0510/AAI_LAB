from __future__ import annotations
from pathlib import Path
import re

def map_tests_to_modules(test_files: list[str], source_files: list[str]) -> dict[str, list[str]]:
    """Map tests to source modules using filename, directory, and import-name heuristics."""
    mapping: dict[str, list[str]] = {source: [] for source in source_files}
    for test in test_files:
        t = Path(test)
        stem = re.sub(r"^(test_)?|(_test)$", "", t.stem)
        candidates = []
        for source in source_files:
            s = Path(source)
            source_stem = s.stem
            if source_stem == "__init__": continue
            if stem and (stem == source_stem or source_stem in t.stem or stem in source_stem):
                candidates.append(source)
            elif s.parent.as_posix() in t.parent.as_posix() and t.parent.as_posix() != ".":
                candidates.append(source)
        if not candidates:
            # Unknown names are conservatively associated with all source modules only by the caller's strategy.
            continue
        for source in candidates:
            if test not in mapping[source]: mapping[source].append(test)
    return mapping

def tests_for_changed_files(changed_files: list[str], test_files: list[str], source_files: list[str], dependency_edges: list[dict[str, str]]) -> tuple[list[str], dict[str, list[str]]]:
    changed = set(changed_files)
    affected = set(changed)
    # If changed file A imports B, changing B can affect A; traverse reverse edges to dependents.
    reverse: dict[str, set[str]] = {}
    for edge in dependency_edges:
        reverse.setdefault(edge["target"], set()).add(edge["source"])
    frontier = list(changed)
    while frontier:
        current = frontier.pop()
        for dependent in reverse.get(current, set()):
            if dependent not in affected:
                affected.add(dependent); frontier.append(dependent)
    mapping = map_tests_to_modules(test_files, source_files)
    selected = set()
    for source in affected:
        selected.update(mapping.get(source, []))
    # Direct test changes always select themselves.
    selected.update(path for path in changed if path in test_files)
    return sorted(selected), {k: v for k, v in mapping.items() if v}
