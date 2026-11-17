"""
classifier.py
Rule-based query classifier with explicit rule precedence,
ambiguity detection, and security/outage bypass logic.

Returns:
    dict with keys: intent, complexity, priority, matched_rule, ambiguous
"""

# ---------------------------------------------------------------------------
# Rule table – checked in ORDER (first match wins)
# Each rule: (trigger_words, intent, complexity, priority, rule_name)
# ---------------------------------------------------------------------------
RULES = [
    # ── P1: Security & Outage – always bypass automation ───────────────────
    (
        ["data breach", "security incident", "unauthorised access",
         "unauthorized access", "hacked", "compromised"],
        "Technical Error", "High", "P1", "security_incident"
    ),
    (
        ["application is down", "service outage", "all users", "complete outage",
         "system down", "platform down"],
        "Technical Error", "High", "P1", "service_outage"
    ),

    # ── P2: Unresolved (must come before login/billing to catch "still") ───
    (
        ["still unresolved", "did not work", "still not working",
         "tried everything", "not fixed", "same issue"],
        "Unresolved Issue", "High", "P2", "unresolved_followup"
    ),

    # ── P2: Login / Access ─────────────────────────────────────────────────
    (
        ["cannot log in", "can't log in", "account locked", "locked out",
         "password reset", "forgot password", "sign in", "login failed",
         "authentication failed", "reset my password"],
        "Login / Access", "Medium", "P2", "login_access"
    ),

    # ── P2: Billing (high-urgency keywords bump to P2) ─────────────────────
    (
        ["double charged", "charged twice", "incorrect charge",
         "billing error", "payment failed", "refund urgent"],
        "Billing", "Medium", "P2", "billing_urgent"
    ),

    # ── P3: Billing (standard) ─────────────────────────────────────────────
    (
        ["invoice", "billing", "payment", "subscription", "refund",
         "cancel subscription", "cancel my", "receipt", "charged"],
        "Billing", "Medium", "P3", "billing_standard"
    ),

    # ── P4: Feature Request (before technical error to prevent "dashboard" collision) ─
    (
        ["feature request", "new feature", "add dark mode", "dark mode",
         "suggest", "would be nice", "please add", "roadmap",
         "integrate with", "integration", "slack"],
        "Feature Request", "Low", "P4", "feature_request"
    ),

    # ── P3: Technical Error ────────────────────────────────────────────────
    (
        ["server error", "error code", "500", "crash", "not loading",
         "blank screen", "api key", "token rejected", "export failed",
         "bug report", "system broken", "keeps failing"],
        "Technical Error", "Medium", "P3", "technical_error"
    ),

    # ── P3: Technical Error (broader – second pass after feature request checked) ─
    (
        ["export", "api", "token", "rejected", "dashboard not",
         "not loading", "failed to", "returns error", "gives error"],
        "Technical Error", "Medium", "P3", "technical_error_broad"
    ),

    # ── P3: General Information ────────────────────────────────────────────
    (
        ["what is", "what features", "how do i", "how to",
         "included in", "basic plan", "pro plan", "enterprise",
         "compliance", "soc2", "iso", "gdpr", "team members",
         "add users", "upgrade", "pricing"],
        "General Information", "Low", "P3", "general_info"
    ),
]

# Short queries with no specific signal are ambiguous
AMBIGUOUS_SIGNALS = [
    "it is not working", "not working", "broken", "issue",
    "problem", "help", "???", "something wrong"
]


def classify_query(query_text: str) -> dict:
    """
    Classify a query.  Returns a dict:
      intent, complexity, priority, matched_rule, ambiguous (bool),
      confidence_label (High / Medium / Low).
    """
    text = query_text.lower().strip()

    # ── Ambiguity check ────────────────────────────────────────────────────
    is_ambiguous = False
    if len(text.split()) <= 6:
        is_ambiguous = True
    for signal in AMBIGUOUS_SIGNALS:
        if signal in text and len(text.split()) <= 10:
            is_ambiguous = True
            break

    # ── Rule matching ──────────────────────────────────────────────────────
    for triggers, intent, complexity, priority, rule_name in RULES:
        if any(trigger in text for trigger in triggers):
            confidence_label = _confidence_label(
                is_ambiguous, complexity, priority
            )
            return {
                "intent": intent,
                "complexity": complexity,
                "priority": priority,
                "matched_rule": rule_name,
                "ambiguous": is_ambiguous,
                "confidence_label": confidence_label,
            }

    # ── Default fallback ───────────────────────────────────────────────────
    return {
        "intent": "General Information",
        "complexity": "Low",
        "priority": "P3",
        "matched_rule": "default_fallback",
        "ambiguous": is_ambiguous,
        "confidence_label": "Low" if is_ambiguous else "Medium",
    }


def _confidence_label(ambiguous: bool, complexity: str, priority: str) -> str:
    if ambiguous:
        return "Low"
    if complexity == "High" or priority == "P1":
        return "Medium"
    return "High"
