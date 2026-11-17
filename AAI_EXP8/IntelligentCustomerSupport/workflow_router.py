"""
workflow_router.py
Risk-aware routing engine with explicit decision traces.

Routes:
  AUTO_RESOLVE  – system answers automatically, no human needed
  REVIEW        – human agent reviews before sending response
  ESCALATE      – immediate human escalation, automation blocked

Every decision is accompanied by a human-readable reason string
stored in the ticket for full transparency.
"""

import json


def _load_config(config_path: str = "config.json") -> dict:
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)


def route_query(
    classification: dict,
    resolution,                  # ResolutionResult
    config_path: str = "config.json",
) -> tuple[str, str, str]:
    """
    Determine the route for a classified, resolved query.

    Returns:
        (route, route_reason, assigned_team)
        route: "AUTO_RESOLVE" | "REVIEW" | "ESCALATE"
    """
    cfg = _load_config(config_path)
    intent = classification["intent"]
    priority = classification["priority"]
    complexity = classification["complexity"]
    confidence = resolution.confidence_score
    ambiguous = classification.get("ambiguous", False)
    has_knowledge = resolution.has_knowledge

    auto_min = cfg["confidence_thresholds"]["auto_resolve_min"]
    esc_max = cfg["confidence_thresholds"]["escalate_max"]
    auto_intents = cfg["auto_resolve_intents"]
    always_esc_intents = cfg["always_escalate_intents"]
    always_esc_priorities = cfg["always_escalate_priorities"]
    teams = cfg["teams"]

    assigned_team = teams.get(intent, "General Support Team")

    # ── Rule 1: Security / P1 always escalate ─────────────────────────────
    if priority in always_esc_priorities:
        return (
            "ESCALATE",
            f"Priority {priority} detected – "
            f"{classification.get('matched_rule', 'critical rule')} triggered. "
            f"Automation is blocked for critical incidents. "
            f"Immediate human escalation required.",
            assigned_team,
        )

    # ── Rule 2: Unresolved issue always escalates ──────────────────────────
    if intent in always_esc_intents:
        return (
            "ESCALATE",
            f"Intent '{intent}' requires human review. "
            f"Previous automated resolution may have failed. "
            f"Escalating to senior support.",
            assigned_team,
        )

    # ── Rule 3: Ambiguous queries go to review ─────────────────────────────
    if ambiguous:
        return (
            "REVIEW",
            f"Query is ambiguous (short or generic phrasing). "
            f"Classification confidence: {classification.get('confidence_label', 'Low')}. "
            f"Human review required before responding.",
            assigned_team,
        )

    # ── Rule 4: No knowledge base match → cannot auto-resolve ─────────────
    if not has_knowledge:
        return (
            "REVIEW",
            f"No approved knowledge base article found for this query "
            f"(retrieval score: {confidence:.0%}). "
            f"Human agent must draft a response from scratch.",
            assigned_team,
        )

    # ── Rule 5: Low confidence → escalate if also high complexity ─────────
    if confidence <= esc_max and complexity == "High":
        return (
            "ESCALATE",
            f"Low retrieval confidence ({confidence:.0%}) combined with "
            f"high complexity. Cannot safely automate a response.",
            assigned_team,
        )

    # ── Rule 6: Low confidence but not high complexity → review ───────────
    if confidence <= esc_max:
        return (
            "REVIEW",
            f"Retrieval confidence ({confidence:.0%}) is below threshold "
            f"({esc_max:.0%}). Human review needed before sending response.",
            assigned_team,
        )

    # ── Rule 7: Auto-resolvable intents with high confidence ──────────────
    if intent in auto_intents and confidence >= auto_min:
        return (
            "AUTO_RESOLVE",
            f"Intent '{intent}' is permitted for automated resolution. "
            f"Retrieval confidence {confidence:.0%} exceeds threshold "
            f"({auto_min:.0%}). Approved article: {resolution.top_match.article_id if resolution.top_match else 'N/A'}.",
            assigned_team,
        )

    # ── Rule 8: Medium confidence → review ────────────────────────────────
    if confidence < auto_min:
        return (
            "REVIEW",
            f"Retrieval confidence ({confidence:.0%}) is below auto-resolve "
            f"threshold ({auto_min:.0%}). Sending to human review queue.",
            assigned_team,
        )

    # ── Default: review ────────────────────────────────────────────────────
    return (
        "REVIEW",
        f"Query does not meet automated resolution criteria. "
        f"Routed to '{assigned_team}' for manual handling.",
        assigned_team,
    )
