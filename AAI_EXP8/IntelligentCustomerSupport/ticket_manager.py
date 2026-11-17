"""
ticket_manager.py
Creates and manages support tickets in SQLite (tickets.db).

Ticket lifecycle:
  OPEN → IN_REVIEW → RESOLVED
                   → ESCALATED → RESOLVED
                   → ON_HOLD   → IN_REVIEW
  OPEN → AUTO_RESOLVED
  OPEN → ESCALATED
"""

import sqlite3
import uuid
import json
from datetime import datetime, timezone
from typing import Optional

DB_PATH = "tickets.db"

# Status constants
STATUS_OPEN = "OPEN"
STATUS_IN_REVIEW = "IN_REVIEW"
STATUS_ESCALATED = "ESCALATED"
STATUS_AUTO_RESOLVED = "AUTO_RESOLVED"
STATUS_ON_HOLD = "ON_HOLD"
STATUS_RESOLVED = "RESOLVED"

VALID_TRANSITIONS = {
    STATUS_OPEN: [STATUS_IN_REVIEW, STATUS_ESCALATED, STATUS_AUTO_RESOLVED],
    STATUS_IN_REVIEW: [STATUS_RESOLVED, STATUS_ESCALATED, STATUS_ON_HOLD],
    STATUS_ESCALATED: [STATUS_RESOLVED, STATUS_IN_REVIEW],
    STATUS_ON_HOLD: [STATUS_IN_REVIEW, STATUS_RESOLVED],
    STATUS_AUTO_RESOLVED: [STATUS_OPEN],   # re-open
    STATUS_RESOLVED: [STATUS_OPEN],         # re-open
}


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they do not exist."""
    conn = _connect()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tickets (
            ticket_id     TEXT PRIMARY KEY,
            query_id      TEXT NOT NULL,
            customer_id   TEXT NOT NULL,
            query_text    TEXT NOT NULL,
            intent        TEXT,
            complexity    TEXT,
            priority      TEXT,
            status        TEXT NOT NULL DEFAULT 'OPEN',
            assigned_team TEXT,
            route         TEXT,
            route_reason  TEXT,
            confidence    REAL,
            article_id    TEXT,
            article_title TEXT,
            proposed_response TEXT,
            reviewer_action   TEXT,
            reviewer_note     TEXT,
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL,
            sla_deadline  TEXT
        );

        CREATE TABLE IF NOT EXISTS ticket_history (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id     TEXT NOT NULL,
            changed_at    TEXT NOT NULL,
            actor         TEXT NOT NULL,
            from_status   TEXT,
            to_status     TEXT,
            note          TEXT
        );
    """)
    conn.commit()
    conn.close()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create_ticket(
    query_id: str,
    customer_id: str,
    query_text: str,
    classification: dict,
    resolution,          # ResolutionResult
    route: str,
    route_reason: str,
    assigned_team: str,
    sla_deadline: str,
) -> dict:
    """Insert a new ticket and return it as a dict."""
    ticket_id = "TKT-" + uuid.uuid4().hex[:6].upper()
    now = _now_iso()

    top = resolution.top_match
    ticket = {
        "ticket_id": ticket_id,
        "query_id": query_id,
        "customer_id": customer_id,
        "query_text": query_text,
        "intent": classification["intent"],
        "complexity": classification["complexity"],
        "priority": classification["priority"],
        "status": STATUS_OPEN,
        "assigned_team": assigned_team,
        "route": route,
        "route_reason": route_reason,
        "confidence": resolution.confidence_score,
        "article_id": top.article_id if top else None,
        "article_title": top.title if top else None,
        "proposed_response": resolution.proposed_response,
        "reviewer_action": None,
        "reviewer_note": None,
        "created_at": now,
        "updated_at": now,
        "sla_deadline": sla_deadline,
    }

    conn = _connect()
    conn.execute(
        """INSERT INTO tickets VALUES (
            :ticket_id, :query_id, :customer_id, :query_text,
            :intent, :complexity, :priority, :status,
            :assigned_team, :route, :route_reason, :confidence,
            :article_id, :article_title, :proposed_response,
            :reviewer_action, :reviewer_note,
            :created_at, :updated_at, :sla_deadline
        )""",
        ticket,
    )
    conn.execute(
        """INSERT INTO ticket_history
           (ticket_id, changed_at, actor, from_status, to_status, note)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (ticket_id, now, "system", None, STATUS_OPEN, "Ticket created"),
    )
    conn.commit()
    conn.close()
    return ticket


def transition_status(
    ticket_id: str,
    new_status: str,
    actor: str = "system",
    note: str = "",
) -> dict:
    """Move a ticket to a new status (validates transition)."""
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)
    ).fetchone()
    if not row:
        conn.close()
        raise ValueError(f"Ticket {ticket_id} not found")

    current_status = row["status"]
    allowed = VALID_TRANSITIONS.get(current_status, [])
    if new_status not in allowed:
        conn.close()
        raise ValueError(
            f"Invalid transition {current_status} → {new_status} "
            f"for ticket {ticket_id}"
        )

    now = _now_iso()
    conn.execute(
        "UPDATE tickets SET status = ?, updated_at = ? WHERE ticket_id = ?",
        (new_status, now, ticket_id),
    )
    conn.execute(
        """INSERT INTO ticket_history
           (ticket_id, changed_at, actor, from_status, to_status, note)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (ticket_id, now, actor, current_status, new_status, note),
    )
    conn.commit()
    updated = dict(conn.execute(
        "SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)
    ).fetchone())
    conn.close()
    return updated


def save_reviewer_action(
    ticket_id: str,
    action: str,
    note: str,
    edited_response: Optional[str] = None,
) -> dict:
    """Record a human reviewer's decision on a ticket."""
    conn = _connect()
    now = _now_iso()
    if edited_response:
        conn.execute(
            """UPDATE tickets
               SET reviewer_action = ?, reviewer_note = ?,
                   proposed_response = ?, updated_at = ?
               WHERE ticket_id = ?""",
            (action, note, edited_response, now, ticket_id),
        )
    else:
        conn.execute(
            """UPDATE tickets
               SET reviewer_action = ?, reviewer_note = ?, updated_at = ?
               WHERE ticket_id = ?""",
            (action, note, now, ticket_id),
        )
    conn.commit()
    row = dict(conn.execute(
        "SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)
    ).fetchone())
    conn.close()
    return row


def get_all_tickets() -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM tickets ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_ticket(ticket_id: str) -> Optional[dict]:
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_ticket_history(ticket_id: str) -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM ticket_history WHERE ticket_id = ? ORDER BY changed_at",
        (ticket_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
