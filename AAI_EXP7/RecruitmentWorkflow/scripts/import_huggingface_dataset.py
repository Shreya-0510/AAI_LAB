"""Optional importer for uhfew/recruitment_data. Install datasets with `uv add datasets` first."""
import csv, random
from pathlib import Path
from datasets import load_dataset

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "candidates.csv"

def overlap_score(required, candidate):
    req = {str(x).strip().lower() for x in (required or []) if str(x).strip()}
    got = {str(x).strip().lower() for x in (candidate or []) if str(x).strip()}
    return round(100 * len(req & got) / len(req), 2) if req else 50.0

def main():
    dataset = load_dataset("uhfew/recruitment_data")
    source = []
    for split in dataset:
        source.extend(dataset[split])
    rows = []
    rng = random.Random(19)
    for i, item in enumerate(source, 1):
        position = str(item.get("opening_position", "")).strip()
        if position and not any(k in position.lower() for k in ("software", "developer", "engineer", "program")):
            continue
        skills = overlap_score(item.get("keywords_for_recruitment"), item.get("keywords_from_applicants"))
        years = max(0, int(float(item.get("experience_years") or 0)))
        experience = min(100, years * 20)
        # Source does not provide a real assessment score: this is an explicitly synthetic proxy.
        assessment = round(min(100, max(0, 0.65 * skills + 0.35 * experience)), 2)
        rows.append({
            "candidate_id": f"HF{i:05d}", "candidate_name": f"Candidate {i:05d}",
            "email": f"candidate{i:05d}@example.com", "skills_score": skills,
            "experience_score": experience, "assessment_score": assessment,
            "application_role": "Junior Software Developer",
            "source_position": position or "Unspecified",
            "cv_summary": str(item.get("cv", ""))[:1200],
            "source_result": str(item.get("result", "")),
            "source_result_reason": str(item.get("reason_for_result", ""))[:500],
        })
    if len(rows) < 100:
        raise RuntimeError(f"Only mapped {len(rows)} records; expected at least 100.")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    print(f"Wrote {len(rows)} records to {OUTPUT}")
    print("Assessment scores are synthetic proxies, not observed test results.")

if __name__ == "__main__":
    main()
