"""
app.py
Core processing pipeline for the Intelligent Customer Support System.

Run directly to process queries from CSV and print a summary:
    uv run python app.py

Or import process_queries() from the Streamlit dashboard.
"""

import csv
import json
import os
import sys
from datetime import datetime, timezone

from audit_logger import log_event
from classifier import classify_query
from notifications import send_notification
from resolver import resolve
from sla_monitor import calculate_deadline
from ticket_manager import (
    create_ticket,
    get_all_tickets,
    init_db,
    transition_status,
    STATUS_AUTO_RESOLVED,
    STATUS_ESCALATED,
    STATUS_IN_REVIEW,
)
from workflow_router import route_query

# ── Constants ──────────────────────────────────────────────────────────────
REQUIRED_FIELDS = {"query_id", "customer_id", "query_text", "created_at"}
REJECTED_LOG = "rejected_queries.csv"


# ---------------------------------------------------------------------------
# Step 1 + 2: Ingestion and Validation
# ---------------------------------------------------------------------------

def ingest_queries(file_path: str) -> tuple[list[dict], list[dict]]:
    """
    Read and validate queries from a CSV file.

    Returns:
        (valid_queries, rejected_queries)
    """
    valid_queries: list[dict] = []
    rejected_queries: list[dict] = []
    seen_ids: set[str] = set()

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Query file not found: {file_path}")

    with open(file_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        if not reader.fieldnames or not REQUIRED_FIELDS.issubset(
            set(reader.fieldnames)
        ):
            raise ValueError(
                f"CSV is missing required columns. Expected: {REQUIRED_FIELDS}"
            )

        for row in reader:
            row = {k: (v or "").strip() for k, v in row.items()}
            errors: list[str] = []

            if not all(row.get(f) for f in REQUIRED_FIELDS):
                errors.append("Missing required field")

            query_id = row.get("query_id", "")
            if query_id in seen_ids:
                errors.append(f"Duplicate query_id: {query_id}")
            else:
                seen_ids.add(query_id)

            if not row.get("query_text", "").strip():
                errors.append("Empty query_text")

            if errors:
                rejected_queries.append({"record": row, "errors": errors})
                log_event(
                    "VALIDATION_FAILED",
                    f"Rejected: {'; '.join(errors)}",
                    query_id=query_id,
                )
            else:
                valid_queries.append(row)

    _write_rejected_log(rejected_queries)
    return valid_queries, rejected_queries


def _write_rejected_log(rejected: list[dict]):
    if not rejected:
        return
    with open(REJECTED_LOG, "w", newline="", encoding="utf-8") as f:
        fieldnames = ["query_id", "customer_id", "query_text", "created_at", "errors"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for item in rejected:
            r = item["record"]
            writer.writerow({
                "query_id": r.get("query_id", ""),
                "customer_id": r.get("customer_id", ""),
                "query_text": r.get("query_text", ""),
                "created_at": r.get("created_at", ""),
                "errors": "; ".join(item["errors"]),
            })


# ---------------------------------------------------------------------------
# Main pipeline: process one query end-to-end
# ---------------------------------------------------------------------------

def process_query(query: dict, config_path: str = "config.json") -> dict:
    """
    Run one valid query through the full pipeline.
    Returns a result dict summarising every decision made.
    """
    query_id = query["query_id"]
    customer_id = query["customer_id"]
    query_text = query["query_text"]
    created_at = query.get("created_at", datetime.now(timezone.utc).isoformat())

    # Step 3: Classify
    classification = classify_query(query_text)
    log_event(
        "CLASSIFIED",
        f"Intent={classification['intent']} | Priority={classification['priority']} | "
        f"Rule={classification['matched_rule']}",
        query_id=query_id,
    )

    # Step 4: Resolve (TF-IDF retrieval)
    resolution = resolve(query_id, query_text)
    log_event(
        "RETRIEVED",
        f"Article={resolution.top_match.article_id if resolution.top_match else 'None'} | "
        f"TF-IDF={resolution.confidence_score:.3f} | "
        f"Baseline={resolution.baseline_score:.3f}",
        query_id=query_id,
    )

    # Step 5: Route
    route, route_reason, assigned_team = route_query(classification, resolution, config_path)
    log_event(
        "ROUTED",
        f"Route={route} | Team={assigned_team} | Reason={route_reason[:120]}",
        query_id=query_id,
    )

    # Step 6: SLA deadline
    sla_deadline = calculate_deadline(classification["priority"], created_at)

    # Step 7: Create ticket
    ticket = create_ticket(
        query_id=query_id,
        customer_id=customer_id,
        query_text=query_text,
        classification=classification,
        resolution=resolution,
        route=route,
        route_reason=route_reason,
        assigned_team=assigned_team,
        sla_deadline=sla_deadline,
    )
    ticket_id = ticket["ticket_id"]
    log_event(
        "TICKET_CREATED",
        f"Status=OPEN | Route={route}",
        ticket_id=ticket_id,
        query_id=query_id,
    )

    # Step 8: Status transition
    if route == "AUTO_RESOLVE":
        ticket = transition_status(ticket_id, STATUS_AUTO_RESOLVED, actor="system",
                                   note="Automated resolution applied")
        notif_type = "auto_resolved"
    elif route == "ESCALATE":
        ticket = transition_status(ticket_id, STATUS_ESCALATED, actor="system",
                                   note=route_reason[:200])
        notif_type = "escalation"
    else:
        ticket = transition_status(ticket_id, STATUS_IN_REVIEW, actor="system",
                                   note="Queued for human review")
        notif_type = "ticket_created"

    log_event(
        "STATUS_TRANSITION",
        f"OPEN → {ticket['status']}",
        ticket_id=ticket_id,
        query_id=query_id,
        previous_value="OPEN",
        new_value=ticket["status"],
    )

    # Step 9: Notification
    notif_result = send_notification(
        ticket_id=ticket_id,
        query_id=query_id,
        customer_id=customer_id,
        notification_type=notif_type,
        priority=classification["priority"],
        proposed_response=resolution.proposed_response,
        recipient=f"{customer_id.lower()}@customer.example.com",
    )
    log_event(
        "NOTIFICATION",
        f"Type={notif_type} | Status={notif_result['final_status']} | "
        f"Attempts={notif_result['total_attempts']}",
        ticket_id=ticket_id,
        query_id=query_id,
    )

    return {
        "query_id": query_id,
        "ticket_id": ticket_id,
        "customer_id": customer_id,
        "query_text": query_text,
        "classification": classification,
        "resolution": {
            "article_id": resolution.top_match.article_id if resolution.top_match else None,
            "article_title": resolution.top_match.title if resolution.top_match else None,
            "tfidf_score": resolution.confidence_score,
            "baseline_score": resolution.baseline_score,
            "matched_terms": resolution.top_match.matched_terms if resolution.top_match else [],
            "has_knowledge": resolution.has_knowledge,
            "proposed_response": resolution.proposed_response,
        },
        "route": route,
        "route_reason": route_reason,
        "assigned_team": assigned_team,
        "status": ticket["status"],
        "sla_deadline": sla_deadline,
        "notification": notif_result,
    }


def process_queries(
    file_path: str = "customer_queries.csv",
    config_path: str = "config.json",
) -> tuple[list[dict], list[dict], list[dict]]:
    """
    Full pipeline: ingest → validate → classify → resolve → route → ticket → notify.

    Returns:
        (results, valid_queries, rejected_queries)
    """
    init_db()
    valid, rejected = ingest_queries(file_path)
    results = []
    for q in valid:
        try:
            result = process_query(q, config_path)
            results.append(result)
        except Exception as exc:
            log_event("PROCESSING_ERROR", str(exc), query_id=q.get("query_id", "?"))
            print(f"[ERROR] Failed to process {q.get('query_id')}: {exc}", file=sys.stderr)
    return results, valid, rejected


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("  Intelligent Customer Support System")
    print("=" * 60)

    results, valid, rejected = process_queries()

    print(f"\n✓ Ingested   : {len(valid)} valid queries")
    print(f"✗ Rejected   : {len(rejected)} invalid queries\n")

    route_counts: dict[str, int] = {}
    for r in results:
        route_counts[r["route"]] = route_counts.get(r["route"], 0) + 1

    print("── Routing Summary ────────────────────────────────────")
    for route, count in route_counts.items():
        print(f"  {route:<20} {count}")

    print("\n── Ticket Details ─────────────────────────────────────")
    for r in results:
        clf = r["classification"]
        res = r["resolution"]
        print(
            f"  {r['ticket_id']} | {clf['priority']} | {r['route']:<13} | "
            f"{clf['intent']:<20} | "
            f"TF-IDF: {res['tfidf_score']:.2f} | "
            f"Baseline: {res['baseline_score']:.2f} | "
            f"Q:{r['query_id']}"
        )

    print(f"\n✓ Audit log  : audit_log.csv")
    print(f"✓ Notif log  : notification_log.csv")
    print(f"✓ Tickets DB : tickets.db")
    print(f"✓ Rejected   : rejected_queries.csv")
    print("\nRun `uv run streamlit run dashboard.py` for the full UI.")
