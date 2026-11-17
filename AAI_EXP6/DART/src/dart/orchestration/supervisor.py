from __future__ import annotations
import time
import uuid
from pathlib import Path
from dart.mcp_client.connection import call_mcp_tool
from dart.llm.planner import create_plan
from dart.orchestration.validator import validate_plan
from dart.orchestration.policy import validate_execution_policy
from dart.orchestration.recovery import classify_failure
from dart.observability.tracing import TraceRecorder
from dart.evaluation.scoring import calculate_run_metrics
async def analyze_repository_workflow(repository: str, base_ref: str | None = None, head_ref: str | None = "HEAD") -> dict:
    trace = TraceRecorder()
    snapshot = await trace.call("inspect_repository", call_mcp_tool, "inspect_repository", {"repository": repository})
    changes = await trace.call("get_changed_files", call_mcp_tool, "get_changed_files", {"repository": repository, "base_ref": base_ref, "head_ref": head_ref})
    dependencies = await trace.call("analyze_dependencies_tool", call_mcp_tool, "analyze_dependencies_tool", {"repository": repository})
    merged = {**snapshot, **changes, "dependency_edges": dependencies.get("edges", []), "dependency_edge_count": dependencies.get("edge_count", 0), "dependency_limitations": dependencies.get("limitations", ""), "mcp_status": "connected"}
    plan = create_plan(merged, "hybrid")
    merged["planner_summary"] = plan.get("rationale", "")
    merged["planner_mode"] = plan.get("planner_mode", "unknown")
    merged["suggested_tests"] = plan.get("selected_tests", [])
    merged["trace"] = trace.records
    return merged

async def execute_strategy_workflow(repository: str, analysis: dict, strategy: str, timeout_seconds: int = 120) -> dict:
    started = time.perf_counter()
    run_id = str(uuid.uuid4())[:8]
    trace = TraceRecorder()
    if strategy == "full_suite":
        raw_plan = {"selected_tests": analysis.get("test_files", []), "rationale": "Run all discovered test files as baseline.", "confidence": 1.0, "evidence_files": [], "planner_mode": "baseline"}
    else:
        raw_plan = create_plan(analysis, strategy)
    validation = validate_plan(raw_plan, analysis.get("test_files", []))
    policy = validate_execution_policy(validation["selected_tests"], analysis.get("test_files", []), approved=True)
    if not policy["allowed"]:
        execution = {"status": "blocked", "output": "; ".join(policy["reasons"]), "duration_seconds": 0, "passed": 0, "failed": 0, "errors": 0, "skipped": 0, "timed_out": False}
    else:
        execution = await trace.call("run_selected_tests", call_mcp_tool, "run_selected_tests", {"repository": repository, "selected_tests": policy["valid_tests"], "timeout_seconds": timeout_seconds, "approved": True})
        execution["execution_backend"] = "mcp"
    duration = time.perf_counter() - started
    metrics = calculate_run_metrics(len(analysis.get("test_files", [])), len(policy.get("valid_tests", [])), execution, duration)
    return {"run_id": run_id, "strategy": strategy, "repository": repository, "commit_hash": analysis.get("commit_hash", "unknown"), "status": execution.get("status", "unknown"), "planner_mode": raw_plan.get("planner_mode", "unknown"), "plan": raw_plan, "validation": validation, "policy": policy, "execution": execution, "metrics": metrics, "trace": trace.records, "recovery": classify_failure(execution), "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
