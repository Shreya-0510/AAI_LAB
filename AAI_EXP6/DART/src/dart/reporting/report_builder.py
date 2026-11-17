from __future__ import annotations
import csv
import json
from pathlib import Path
from datetime import datetime

def save_run_report(record: dict, artifacts_dir: Path | str) -> dict:
    root = Path(artifacts_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    run_id = str(record.get("run_id", "run"))
    json_path = root / f"{run_id}_{record.get('strategy', 'strategy')}.json"
    json_path.write_text(json.dumps(record, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    csv_path = root / "runs_summary.csv"
    row = {"run_id": run_id, "strategy": record.get("strategy"), "repository": record.get("repository"), "commit_hash": record.get("commit_hash"), **record.get("metrics", {})}
    exists = csv_path.exists()
    with csv_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row.keys()), extrasaction="ignore")
        if not exists: writer.writeheader()
        writer.writerow(row)
    return {"json_path": str(json_path), "csv_path": str(csv_path)}

def build_summary(records: list[dict]) -> dict:
    return {"generated_at": datetime.now().isoformat(), "run_count": len(records), "runs": records, "interpretation_note": "Use controlled fault scenarios to assess regression-detection effectiveness; selected-test reduction alone is insufficient."}
