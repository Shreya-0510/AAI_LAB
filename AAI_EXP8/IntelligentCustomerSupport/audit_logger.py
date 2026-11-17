"""
audit_logger.py
Records every decision, state change, retry, and error to audit_log.csv.
"""

import csv
import os
from datetime import datetime

AUDIT_LOG_PATH = "audit_log.csv"
AUDIT_FIELDS = [
    "timestamp", "ticket_id", "query_id", "event_type",
    "actor", "detail", "previous_value", "new_value"
]


def _ensure_header():
    if not os.path.exists(AUDIT_LOG_PATH):
        with open(AUDIT_LOG_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=AUDIT_FIELDS)
            writer.writeheader()


def log_event(
    event_type: str,
    detail: str,
    ticket_id: str = "",
    query_id: str = "",
    actor: str = "system",
    previous_value: str = "",
    new_value: str = "",
):
    """Append one audit event to audit_log.csv."""
    _ensure_header()
    row = {
        "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "ticket_id": ticket_id,
        "query_id": query_id,
        "event_type": event_type,
        "actor": actor,
        "detail": detail,
        "previous_value": previous_value,
        "new_value": new_value,
    }
    with open(AUDIT_LOG_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=AUDIT_FIELDS)
        writer.writerow(row)
