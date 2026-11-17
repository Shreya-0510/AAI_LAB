import json
from pathlib import Path
import pytest
from recruitment_workflow import (load_rules, route_candidate, score_candidate,
    validate_candidate, validate_and_deduplicate, generate_notification, review_action)

ROOT = Path(__file__).resolve().parents[1]
@pytest.fixture
def rules():
    return load_rules(ROOT / "rules.json")

def candidate(cid="C001", skills=80, experience=70, assessment=90):
    return {"candidate_id": cid, "candidate_name": "Test Candidate", "email": "test@example.com",
            "skills_score": str(skills), "experience_score": str(experience),
            "assessment_score": str(assessment), "application_role": "Junior Software Developer"}

def test_weighted_score(rules):
    result = score_candidate(candidate(), rules)
    assert result["score"] == 80
    assert result["breakdown"]["skills_score"]["weighted_contribution"] == 32

@pytest.mark.parametrize("score,expected", [
    (75,"SHORTLIST_REVIEW"), (74.99,"MANUAL_REVIEW"), (50,"MANUAL_REVIEW"),
    (49.99,"NOT_SHORTLISTED_REVIEW"), (100,"SHORTLIST_REVIEW"), (0,"NOT_SHORTLISTED_REVIEW")])
def test_thresholds(rules, score, expected):
    assert route_candidate(score, rules) == expected

def test_missing_email():
    row = candidate(); row["email"] = ""
    ok, errors = validate_candidate(row)
    assert not ok and "Missing field: email" in errors

def test_invalid_score():
    ok, errors = validate_candidate(candidate(skills=101))
    assert not ok and any("between 0 and 100" in e for e in errors)

def test_duplicate_quarantined():
    valid, rejected = validate_and_deduplicate([candidate(), candidate()])
    assert len(valid) == 1 and len(rejected) == 1

def test_notification_stays_review_language():
    draft = generate_notification(candidate(), "NOT_SHORTLISTED_REVIEW")
    assert draft["notification_status"] == "DRAFT"
    assert "undergoing review" in draft["message"]

@pytest.mark.parametrize("action,expected", [
    ("APPROVE","SHORTLIST_REVIEW"), ("EDIT","REQUIRES_REVIEW"),
    ("HOLD","ON_HOLD"), ("REQUEST_INFO","AWAITING_INFORMATION")])
def test_review_actions(action, expected):
    assert review_action("SHORTLIST_REVIEW", action) == expected

def test_bad_weights_rejected(tmp_path):
    rules = json.loads((ROOT / "rules.json").read_text())
    rules["criteria"]["skills_score"]["weight"] = 80
    p = tmp_path / "rules.json"; p.write_text(json.dumps(rules))
    with pytest.raises(ValueError):
        load_rules(p)
