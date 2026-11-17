from __future__ import annotations
from pathlib import Path
import json
from datetime import datetime, timezone

def load_benchmark_scenarios(path: str) -> list[dict]:
    file = Path(path)
    if not file.exists(): return []
    data = json.loads(file.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else data.get("scenarios", [])

def benchmark_metadata(repository: str, commit_hash: str, scenario_id: str, strategy: str, repeat: int) -> dict:
    return {"repository": str(Path(repository).resolve()), "commit_hash": commit_hash, "scenario_id": scenario_id, "strategy": strategy, "repeat": repeat, "timestamp": datetime.now(timezone.utc).isoformat()}
