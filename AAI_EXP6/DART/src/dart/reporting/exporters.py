from __future__ import annotations
import json
from pathlib import Path

def export_json(data: dict, destination: str) -> str:
    path = Path(destination).resolve(); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return str(path)
