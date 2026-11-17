SYSTEM_PROMPT = """You are a cautious software test-selection assistant. Return only JSON with keys selected_tests, rationale, confidence, evidence_files. selected_tests must contain only exact paths from the provided discovered_test_files list. Never propose shell commands, arbitrary paths, or tests not in that list. Prefer high-relevance tests but explain uncertainty. Do not claim tests were run."""

def build_user_prompt(changed_files: list[str], diff_text: str, discovered_test_files: list[str], dependency_edges: list[dict], mode: str) -> str:
    import json
    payload = {
        "task": "Select pytest test files likely relevant to the supplied code changes.",
        "strategy": mode,
        "changed_files": changed_files,
        "diff_excerpt": diff_text[:12000],
        "discovered_test_files": discovered_test_files,
        "dependency_edges": dependency_edges[:250] if mode == "hybrid" else [],
        "requirements": ["Return exact test paths from discovered_test_files only.", "If uncertain, choose a conservative subset or all relevant tests.", "State why and name evidence files."],
    }
    return json.dumps(payload, ensure_ascii=False)
