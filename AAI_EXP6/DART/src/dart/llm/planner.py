from __future__ import annotations
from dart.analysis.selection_strategies import heuristic_test_selection
from dart.llm.provider import generate_test_plan, groq_available

def create_plan(analysis: dict, strategy: str) -> dict:
    if strategy not in {"llm_only", "hybrid"}:
        return {"selected_tests": analysis.get("test_files", []), "rationale": "Full-suite baseline selects all discovered test files.", "confidence": 1.0, "evidence_files": [], "planner_mode": "baseline", "model": None}
    static_selected = heuristic_test_selection(analysis.get("changed_files", []), analysis.get("test_files", []), analysis.get("python_files", []), analysis.get("dependency_edges", []))
    if groq_available():
        try:
            plan = generate_test_plan(analysis.get("changed_files", []), analysis.get("diff_text", ""), analysis.get("test_files", []), analysis.get("dependency_edges", []), strategy)
            if strategy == "hybrid":
                # Hybrid DART preserves both the LLM suggestions and statically mapped tests.
                llm_selected = plan.get("selected_tests", [])
                plan["selected_tests"] = sorted(set(llm_selected) | set(static_selected))
                plan["rationale"] = str(plan.get("rationale", "")) + " Hybrid supervisor merged the LLM recommendations with static dependency/test mapping."
                plan["static_recommendations"] = static_selected
            plan["planner_mode"] = "groq_llm_hybrid" if strategy == "hybrid" else "groq_llm_only"
            return plan
        except Exception as exc:
            # Explicitly surface the fallback reason; never silently label it as LLM output.
            fallback = sorted(set(static_selected)) if strategy == "hybrid" else static_selected
            return {"selected_tests": fallback, "rationale": f"Groq planner failed; heuristic fallback used. Reason: {type(exc).__name__}: {exc}", "confidence": 0.35, "evidence_files": analysis.get("changed_files", []), "planner_mode": "heuristic_fallback_after_llm_error", "model": None}
    selected = sorted(set(static_selected)) if strategy == "hybrid" else static_selected
    return {"selected_tests": selected, "rationale": "No Groq API key configured. Selected tests using static dependency and filename heuristics; this is not an LLM result.", "confidence": 0.35, "evidence_files": analysis.get("changed_files", []), "planner_mode": "heuristic_no_api_key", "model": None}
