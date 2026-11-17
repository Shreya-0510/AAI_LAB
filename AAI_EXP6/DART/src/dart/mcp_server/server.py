from __future__ import annotations
import json
import os
from pathlib import Path
import sys

from mcp.server.fastmcp import FastMCP

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
from dart.analysis.git_diff import repository_snapshot  # noqa: E402
from dart.analysis.dependency_graph import analyze_dependencies  # noqa: E402
from dart.analysis.test_mapping import tests_for_changed_files  # noqa: E402
from dart.analysis.selection_strategies import validate_test_paths  # noqa: E402
from dart.execution.pytest_runner import run_pytest  # noqa: E402
from dart.config import get_settings  # noqa: E402

mcp = FastMCP("DART Dependency-Aware Regression Testing")

@mcp.tool()
def inspect_repository(repository: str) -> dict:
    """Inspect a local repository and report Python files, tests, and current commit."""
    return repository_snapshot(repository)

@mcp.tool()
def get_changed_files(repository: str, base_ref: str | None = None, head_ref: str | None = "HEAD") -> dict:
    """Get changed files and a bounded diff for a commit range or worktree."""
    snap = repository_snapshot(repository, base_ref, head_ref)
    return {"changed_files": snap["changed_files"], "diff_text": snap["diff_text"], "commit_hash": snap["commit_hash"], "git_available": snap["git_available"]}

@mcp.tool()
def read_diff(repository: str, base_ref: str | None = None, head_ref: str | None = "HEAD") -> dict:
    """Read a bounded git diff for the repository."""
    snap = repository_snapshot(repository, base_ref, head_ref)
    return {"diff_text": snap["diff_text"], "changed_files": snap["changed_files"]}

@mcp.tool()
def analyze_dependencies_tool(repository: str) -> dict:
    """Analyze internal Python imports using the AST; dynamic imports may be missed."""
    return analyze_dependencies(repository)

@mcp.tool()
def discover_tests(repository: str) -> dict:
    """Discover Python pytest test files by common filename and directory conventions."""
    snap = repository_snapshot(repository)
    return {"test_files": snap["test_files"], "count": len(snap["test_files"])}

@mcp.tool()
def map_tests_to_modules(repository: str, changed_files: list[str]) -> dict:
    """Map tests to changed modules using static dependencies and filename heuristics."""
    snap = repository_snapshot(repository)
    deps = analyze_dependencies(repository)
    selected, mapping = tests_for_changed_files(changed_files, snap["test_files"], snap["python_files"], deps["edges"])
    return {"selected_tests": selected, "mapping": mapping, "limitations": "Heuristic mapping; may miss dynamic/runtime dependencies."}

@mcp.tool()
def validate_test_plan(repository: str, selected_tests: list[str]) -> dict:
    """Reject test paths that are not in the repository's discovered test-file allowlist."""
    snap = repository_snapshot(repository)
    valid, rejected = validate_test_paths(selected_tests, snap["test_files"])
    return {"valid_tests": valid, "rejected_tests": rejected, "allowed_count": len(snap["test_files"])}

@mcp.tool()
def run_selected_tests(repository: str, selected_tests: list[str], timeout_seconds: int = 120, approved: bool = False) -> dict:
    """Run explicitly approved, discovered pytest files. This executes repository code."""
    if not approved:
        return {"status": "blocked", "error": "Execution requires explicit approval from the caller.", "return_code": None}
    snap = repository_snapshot(repository)
    valid, rejected = validate_test_paths(selected_tests, snap["test_files"])
    if rejected:
        return {"status": "rejected", "error": "One or more test targets were not allowlisted.", "rejected_tests": rejected, "return_code": None}
    if not valid:
        return {"status": "rejected", "error": "No valid test files selected.", "return_code": None}
    return run_pytest(repository, valid, timeout_seconds=timeout_seconds)

@mcp.tool()
def get_test_results(run_result: dict) -> dict:
    """Normalize the result payload from a pytest execution."""
    return {key: run_result.get(key) for key in ("status", "return_code", "duration_seconds", "passed", "failed", "errors", "skipped", "output", "timed_out")}

@mcp.tool()
def generate_experiment_report(run_records: list[dict]) -> dict:
    """Create a compact, JSON-serializable summary from strategy run records."""
    return {"run_count": len(run_records), "runs": run_records, "note": "Interpret selection reduction separately from defect-detection effectiveness."}

if __name__ == "__main__":
    mcp.run(transport="stdio")
