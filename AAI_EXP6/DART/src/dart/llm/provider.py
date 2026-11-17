from __future__ import annotations
import json
from groq import Groq
from dart.config import get_settings
from dart.llm.prompts import SYSTEM_PROMPT, build_user_prompt

def groq_available() -> bool:
    return bool(get_settings().groq_api_key)

def generate_test_plan(changed_files: list[str], diff_text: str, test_files: list[str], dependency_edges: list[dict], mode: str) -> dict:
    settings = get_settings()
    if not settings.groq_api_key:
        raise RuntimeError("Groq API key is not configured; use the explicitly labeled heuristic planner instead.")
    client = Groq(api_key=settings.groq_api_key)
    response = client.chat.completions.create(
        model=settings.groq_model,
        temperature=0.1,
        max_tokens=1800,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": build_user_prompt(changed_files, diff_text, test_files, dependency_edges, mode)}],
    )
    content = response.choices[0].message.content or "{}"
    try: parsed = json.loads(content)
    except json.JSONDecodeError as exc: raise ValueError(f"Groq returned invalid JSON: {exc}") from exc
    return {"selected_tests": parsed.get("selected_tests", []), "rationale": str(parsed.get("rationale", "")), "confidence": parsed.get("confidence", 0.5), "evidence_files": parsed.get("evidence_files", []), "model": settings.groq_model}
