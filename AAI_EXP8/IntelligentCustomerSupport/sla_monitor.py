"""
sla_monitor.py
Calculates SLA deadlines and identifies overdue tickets.
"""

import json
from datetime import datetime, timezone, timedelta
from typing import Optional


def _load_sla_config(config_path: str = "config.json") -> dict:
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)["sla_hours"]


def calculate_deadline(priority: str, created_at: str, config_path: str = "config.json") -> str:
    """Return ISO-8601 deadline string for the given priority and creation time."""
    sla_hours = _load_sla_config(config_path)
    hours = sla_hours.get(priority, 24)

    # Parse created_at – accept both with and without trailing Z
    created_at_clean = created_at.replace("Z", "+00:00")
    try:
        created_dt = datetime.fromisoformat(created_at_clean)
    except ValueError:
        # Fallback: treat as naive UTC
        created_dt = datetime.strptime(created_at[:19], "%Y-%m-%dT%H:%M:%S").replace(
            tzinfo=timezone.utc
        )

    if created_dt.tzinfo is None:
        created_dt = created_dt.replace(tzinfo=timezone.utc)

    deadline = created_dt + timedelta(hours=hours)
    return deadline.isoformat(timespec="seconds")


def check_sla_status(ticket: dict) -> dict:
    """
    Return SLA status for a ticket dict.

    Returns:
        {
          "sla_deadline": str,
          "hours_remaining": float,
          "is_breached": bool,
          "sla_label": "ON TRACK" | "AT RISK" | "BREACHED",
        }
    """
    deadline_str = ticket.get("sla_deadline")
    if not deadline_str:
        return {
            "sla_deadline": None,
            "hours_remaining": None,
            "is_breached": False,
            "sla_label": "UNKNOWN",
        }

    deadline_str_clean = deadline_str.replace("Z", "+00:00")
    try:
        deadline_dt = datetime.fromisoformat(deadline_str_clean)
    except ValueError:
        deadline_dt = datetime.strptime(deadline_str[:19], "%Y-%m-%dT%H:%M:%S").replace(
            tzinfo=timezone.utc
        )

    if deadline_dt.tzinfo is None:
        deadline_dt = deadline_dt.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    remaining = (deadline_dt - now).total_seconds() / 3600
    is_breached = remaining < 0
    resolved = ticket.get("status") in ("RESOLVED", "AUTO_RESOLVED")

    if resolved:
        label = "RESOLVED"
    elif is_breached:
        label = "BREACHED"
    elif remaining < 1.0:
        label = "AT RISK"
    else:
        label = "ON TRACK"

    return {
        "sla_deadline": deadline_str,
        "hours_remaining": round(remaining, 2),
        "is_breached": is_breached and not resolved,
        "sla_label": label,
    }


def get_overdue_tickets(tickets: list[dict]) -> list[dict]:
    """Filter tickets that have breached their SLA."""
    return [
        t for t in tickets
        if check_sla_status(t).get("is_breached", False)
    ]
