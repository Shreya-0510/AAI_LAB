from __future__ import annotations
import csv, json, re, sqlite3, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REQUIRED_FIELDS = ["candidate_id", "candidate_name", "email", "skills_score",
                   "experience_score", "assessment_score", "application_role"]
SCORE_FIELDS = ["skills_score", "experience_score", "assessment_score"]
VALID_REVIEW_ACTIONS = {"APPROVE", "EDIT", "HOLD", "REQUEST_INFO"}
ALLOWED_FINAL_STATUSES = {"SHORTLIST_REVIEW", "MANUAL_REVIEW", "NOT_SHORTLISTED_REVIEW",
                          "REQUIRES_REVIEW", "ON_HOLD", "AWAITING_INFORMATION"}

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def load_rules(path="rules.json") -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        rules = json.load(f)
    criteria = rules.get("criteria", {})
    if set(criteria) != set(SCORE_FIELDS):
        raise ValueError("Rules must define all required scoring criteria.")
    weights = [float(criteria[k]["weight"]) for k in SCORE_FIELDS]
    if any(w < 0 for w in weights) or abs(sum(weights) - 100) > 1e-8:
        raise ValueError("Weights must be non-negative and sum to 100.")
    t = rules.get("thresholds", {})
    short, manual = float(t.get("shortlist_review", -1)), float(t.get("manual_review", -1))
    if not 0 <= manual <= short <= 100:
        raise ValueError("Thresholds must satisfy 0 <= manual <= shortlist <= 100.")
    if not rules.get("rule_version"):
        raise ValueError("rule_version is required.")
    return rules

def load_candidates(path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("CSV is empty or has no header.")
        missing = set(REQUIRED_FIELDS) - set(reader.fieldnames)
        if missing:
            raise ValueError(f"CSV missing required columns: {', '.join(sorted(missing))}")
        return list(reader)

def normalize_candidate(candidate):
    return {str(k): "" if v is None else str(v).strip() for k, v in candidate.items()}

def validate_candidate(candidate) -> tuple[bool, list[str]]:
    row = normalize_candidate(candidate)
    errors = []
    for field in REQUIRED_FIELDS:
        if not row.get(field, "").strip():
            errors.append(f"Missing field: {field}")
    email = row.get("email", "")
    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        errors.append("Invalid email format")
    for field in SCORE_FIELDS:
        raw = row.get(field, "")
        if not raw:
            continue
        try:
            score = float(raw)
        except (ValueError, TypeError):
            errors.append(f"Invalid numeric value: {field}")
            continue
        if not 0 <= score <= 100:
            errors.append(f"{field} must be between 0 and 100")
    return not errors, errors

def validate_and_deduplicate(candidates):
    valid, rejected, seen = [], [], set()
    for line, raw in enumerate(candidates, start=2):
        row = normalize_candidate(raw)
        cid = row.get("candidate_id", "")
        if cid and cid in seen:
            rejected.append({**row, "source_row": line,
                             "rejection_reason": "Duplicate candidate_id; quarantined"})
            continue
        if cid:
            seen.add(cid)
        ok, errors = validate_candidate(row)
        if not ok:
            rejected.append({**row, "source_row": line, "rejection_reason": "; ".join(errors)})
        else:
            valid.append(row)
    return valid, rejected

def score_candidate(candidate, rules):
    breakdown, total = {}, 0.0
    for field in SCORE_FIELDS:
        criterion = rules["criteria"][field]
        input_score, weight = float(candidate[field]), float(criterion["weight"])
        contribution = input_score * weight / 100
        breakdown[field] = {"label": criterion["label"], "input_score": input_score,
                            "weight": weight, "weighted_contribution": round(contribution, 2),
                            "max_contribution": weight}
        total += contribution
    score = round(total, 2)
    if not 0 <= score <= 100:
        raise ValueError("Computed score outside 0–100.")
    return {"score": score, "breakdown": breakdown, "rule_version": rules["rule_version"]}

def route_candidate(score, rules):
    if score >= float(rules["thresholds"]["shortlist_review"]):
        return "SHORTLIST_REVIEW"
    if score >= float(rules["thresholds"]["manual_review"]):
        return "MANUAL_REVIEW"
    return "NOT_SHORTLISTED_REVIEW"

def generate_notification(candidate, status):
    templates = {
        "SHORTLIST_REVIEW": ("Application Update",
            "Your application is being considered for the next stage. The recruitment team will review it and communicate next steps."),
        "MANUAL_REVIEW": ("Application Under Review",
            "Your application is currently under review. The recruitment team will communicate further updates."),
        "NOT_SHORTLISTED_REVIEW": ("Application Review Update",
            "Your application is undergoing review by the recruitment team. You will be informed of the outcome after review."),
    }
    subject, body = templates.get(status, templates["MANUAL_REVIEW"])
    cid = candidate.get("candidate_id", "")
    return {"candidate_id": cid, "subject": subject,
            "message": f"Dear {candidate.get('candidate_name', 'Candidate')},\\n\\n{body}\\n\\nApplication reference: {cid}\\n\\nRegards,\\nRecruitment Team",
            "notification_status": "DRAFT"}

def review_action(proposed_status, action):
    if action not in VALID_REVIEW_ACTIONS:
        raise ValueError("Invalid review action.")
    return {"APPROVE": proposed_status, "EDIT": "REQUIRES_REVIEW",
            "HOLD": "ON_HOLD", "REQUEST_INFO": "AWAITING_INFORMATION"}[action]

def init_db(path="data/recruitment.db"):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS audit_events(
            event_id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL,
            candidate_id TEXT, event_type TEXT NOT NULL, payload_json TEXT NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS applications(
            candidate_id TEXT PRIMARY KEY, candidate_json TEXT NOT NULL, score REAL,
            breakdown_json TEXT, rule_version TEXT, proposed_status TEXT,
            reviewer_action TEXT, final_status TEXT, reviewer_id TEXT, review_notes TEXT,
            notification_status TEXT DEFAULT 'NOT_SENT', updated_at TEXT NOT NULL)""")
        conn.commit()

def audit_event(event_type, candidate_id, payload, db_path="data/recruitment.db"):
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("INSERT INTO audit_events(timestamp,candidate_id,event_type,payload_json) VALUES(?,?,?,?)",
                     (utc_now(), candidate_id, event_type, json.dumps(payload, ensure_ascii=False, default=str)))
        conn.commit()

def process_batch(candidates, rules, db_path="data/recruitment.db"):
    init_db(db_path)
    started = time.perf_counter()
    valid, rejected = validate_and_deduplicate(candidates)
    results = []
    for row in valid:
        scored = score_candidate(row, rules)
        status = route_candidate(scored["score"], rules)
        result = {**row, **scored, "proposed_status": status,
                  "notification": generate_notification(row, status),
                  "reviewer_action": "PENDING", "final_status": "PENDING"}
        results.append(result)
        audit_event("PROPOSAL_CREATED", row["candidate_id"],
                    {"score": scored["score"], "breakdown": scored["breakdown"],
                     "rule_version": scored["rule_version"], "proposed_status": status}, db_path)
        with sqlite3.connect(db_path) as conn:
            conn.execute("""INSERT INTO applications(candidate_id,candidate_json,score,breakdown_json,
                rule_version,proposed_status,reviewer_action,final_status,notification_status,updated_at)
                VALUES(?,?,?,?,?,?,'PENDING','PENDING','NOT_SENT',?)
                ON CONFLICT(candidate_id) DO UPDATE SET candidate_json=excluded.candidate_json,
                score=excluded.score, breakdown_json=excluded.breakdown_json,
                rule_version=excluded.rule_version, proposed_status=excluded.proposed_status,
                updated_at=excluded.updated_at""",
                (row["candidate_id"], json.dumps(row), scored["score"], json.dumps(scored["breakdown"]),
                 scored["rule_version"], status, utc_now()))
            conn.commit()
    for row in rejected:
        audit_event("RECORD_QUARANTINED", row.get("candidate_id"),
                    {"reason": row["rejection_reason"], "source_row": row["source_row"]}, db_path)
    elapsed = time.perf_counter() - started
    return {"results": results, "rejected": rejected, "total_records": len(candidates),
            "valid_records": len(valid), "invalid_records": len(rejected),
            "elapsed_seconds": elapsed, "avg_ms_per_valid": elapsed * 1000 / len(valid) if valid else 0}

def save_rejected_csv(rejected, path="reports/rejected_records.csv"):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({k for row in rejected for k in row}) or ["candidate_id", "rejection_reason"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rejected)

def review_application(candidate_id, action, reviewer_id, notes="", edited_status=None,
                       message_approved=False, db_path="data/recruitment.db", authorized=False):
    if not authorized:
        audit_event("UNAUTHORIZED_REVIEW_DENIED", candidate_id,
                    {"reviewer_id": reviewer_id, "action": action}, db_path)
        raise PermissionError("Reviewer is not authorized.")
    if action not in VALID_REVIEW_ACTIONS:
        raise ValueError("Invalid review action.")
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rec = conn.execute("SELECT * FROM applications WHERE candidate_id=?", (candidate_id,)).fetchone()
        if rec is None:
            raise KeyError(f"Unknown candidate ID: {candidate_id}")
        final = edited_status if action == "EDIT" and edited_status else review_action(rec["proposed_status"], action)
        if final not in ALLOWED_FINAL_STATUSES:
            raise ValueError("Edited status is not allowed.")
        notification_status = "SENT_SIMULATED" if action == "APPROVE" and message_approved else "NOT_SENT"
        conn.execute("""UPDATE applications SET reviewer_action=?,final_status=?,reviewer_id=?,
            review_notes=?,notification_status=?,updated_at=? WHERE candidate_id=?""",
            (action, final, reviewer_id, notes, notification_status, utc_now(), candidate_id))
        conn.commit()
    audit_event("HUMAN_REVIEW_RECORDED", candidate_id,
                {"reviewer_id": reviewer_id, "action": action, "final_status": final,
                 "notes": notes, "message_approved": message_approved,
                 "notification_status": notification_status}, db_path)
    return {"final_status": final, "notification_status": notification_status}
