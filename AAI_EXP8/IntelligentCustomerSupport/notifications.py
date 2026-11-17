"""
notifications.py
Mock notification service with retry logic, failure simulation,
and a persistent notification_log.csv.

No real email credentials needed – delivery is simulated deterministically.
Failure injection: query IDs ending in 0 fail on attempt 1 (to test retries).
"""

import csv
import os
import random
import time
from datetime import datetime, timezone

NOTIFICATION_LOG_PATH = "notification_log.csv"
LOG_FIELDS = [
    "log_id", "ticket_id", "query_id", "notification_type",
    "recipient", "subject", "attempt", "status", "timestamp", "error"
]

_log_counter = [0]  # mutable counter for log IDs


def _ensure_header():
    if not os.path.exists(NOTIFICATION_LOG_PATH):
        with open(NOTIFICATION_LOG_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=LOG_FIELDS)
            writer.writeheader()


def _log_attempt(row: dict):
    _ensure_header()
    _log_counter[0] += 1
    row["log_id"] = f"NLOG-{_log_counter[0]:04d}"
    with open(NOTIFICATION_LOG_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        writer.writerow(row)


def _mock_send(ticket_id: str, query_id: str, attempt: int) -> bool:
    """
    Simulated delivery.
    Queries ending in '0' or '7' will fail on attempt 1 to demonstrate retries.
    """
    if attempt == 1 and (query_id.endswith("0") or query_id.endswith("7")):
        return False   # Simulate transient failure
    return True


def _build_subject(notification_type: str, ticket_id: str, priority: str) -> str:
    if notification_type == "ticket_created":
        return f"[{priority}] Support Ticket Created – {ticket_id}"
    if notification_type == "escalation":
        return f"[ACTION REQUIRED] Ticket Escalated – {ticket_id}"
    if notification_type == "auto_resolved":
        return f"Your Query Has Been Resolved – {ticket_id}"
    if notification_type == "sla_breach":
        return f"[SLA BREACH] Ticket Overdue – {ticket_id}"
    return f"Support Update – {ticket_id}"


def _build_body(
    notification_type: str,
    ticket_id: str,
    customer_id: str,
    priority: str,
    proposed_response: str,
) -> str:
    if notification_type == "ticket_created":
        return (
            f"Dear {customer_id},\n\n"
            f"Your support request has been received.\n"
            f"Ticket ID: {ticket_id} | Priority: {priority}\n\n"
            f"Our team will respond within the SLA timeframe for {priority} tickets.\n\n"
            f"Support Team"
        )
    if notification_type == "auto_resolved":
        return (
            f"Dear {customer_id},\n\n"
            f"We have automatically resolved your query.\n\n"
            f"{proposed_response}\n\n"
            f"If this does not fully address your issue, reply to this email.\n\n"
            f"Support Team"
        )
    if notification_type == "escalation":
        return (
            f"[INTERNAL – {ticket_id}]\n\n"
            f"Ticket {ticket_id} (Priority {priority}) has been escalated.\n"
            f"A senior support engineer must review and respond within SLA.\n\n"
            f"Proposed response drafted:\n{proposed_response}"
        )
    return f"Update on your support ticket {ticket_id}."


def send_notification(
    ticket_id: str,
    query_id: str,
    customer_id: str,
    notification_type: str,
    priority: str,
    proposed_response: str,
    recipient: str,
    max_retries: int = 3,
    retry_delay: float = 0.5,
) -> dict:
    """
    Attempt to send a notification, retrying up to max_retries times.

    Returns a summary dict with final status and attempt count.
    """
    subject = _build_subject(notification_type, ticket_id, priority)
    body = _build_body(
        notification_type, ticket_id, customer_id, priority, proposed_response
    )

    final_status = "FAILED"
    total_attempts = 0
    last_error = ""

    for attempt in range(1, max_retries + 1):
        total_attempts = attempt
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        success = _mock_send(ticket_id, query_id, attempt)

        if success:
            final_status = "DELIVERED"
            _log_attempt({
                "ticket_id": ticket_id,
                "query_id": query_id,
                "notification_type": notification_type,
                "recipient": recipient,
                "subject": subject,
                "attempt": attempt,
                "status": "DELIVERED",
                "timestamp": ts,
                "error": "",
            })
            break
        else:
            last_error = "Simulated transient delivery failure"
            _log_attempt({
                "ticket_id": ticket_id,
                "query_id": query_id,
                "notification_type": notification_type,
                "recipient": recipient,
                "subject": subject,
                "attempt": attempt,
                "status": "FAILED",
                "timestamp": ts,
                "error": last_error,
            })
            if attempt < max_retries:
                time.sleep(retry_delay)

    return {
        "ticket_id": ticket_id,
        "notification_type": notification_type,
        "final_status": final_status,
        "total_attempts": total_attempts,
        "subject": subject,
        "body_preview": body[:200],
    }
