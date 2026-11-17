"""
dashboard.py
Streamlit-based support operations dashboard.

Run:  uv run streamlit run dashboard.py
"""

import json
import os
import pandas as pd
import streamlit as st
from datetime import datetime, timezone

# ── Page config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SupportOps Dashboard",
    page_icon="🎫",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Imports from our modules ───────────────────────────────────────────────
from app import process_queries
from ticket_manager import (
    get_all_tickets, get_ticket, get_ticket_history,
    save_reviewer_action, transition_status,
    STATUS_RESOLVED, STATUS_ESCALATED, STATUS_IN_REVIEW, STATUS_ON_HOLD,
)
from sla_monitor import check_sla_status, get_overdue_tickets
from audit_logger import log_event

# ── Custom CSS ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Typography */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

/* Priority badges */
.badge { display:inline-block; padding:2px 10px; border-radius:4px;
         font-size:12px; font-weight:600; letter-spacing:.4px; }
.badge-P1 { background:#fee2e2; color:#991b1b; }
.badge-P2 { background:#fef3c7; color:#92400e; }
.badge-P3 { background:#dbeafe; color:#1e40af; }
.badge-P4 { background:#f0fdf4; color:#166534; }

/* Route badges */
.route-ESCALATE     { background:#fee2e2; color:#991b1b; }
.route-REVIEW       { background:#fef9c3; color:#854d0e; }
.route-AUTO_RESOLVE { background:#dcfce7; color:#14532d; }

/* SLA badges */
.sla-BREACHED  { background:#fee2e2; color:#991b1b; }
.sla-AT_RISK   { background:#fef3c7; color:#92400e; }
.sla-ON_TRACK  { background:#dcfce7; color:#14532d; }
.sla-RESOLVED  { background:#f3f4f6; color:#6b7280; }

/* Metric cards */
.metric-card { background:#f8fafc; border:1px solid #e2e8f0;
               border-radius:8px; padding:16px 20px; }

/* Decision trace box */
.trace-box { background:#f1f5f9; border-left:4px solid #3b82f6;
             border-radius:4px; padding:12px 16px;
             font-family:'JetBrains Mono',monospace; font-size:13px; }

/* Confidence bar */
.conf-bar-wrap { background:#e2e8f0; border-radius:4px; height:8px; }
.conf-bar { height:8px; border-radius:4px; }
</style>
""", unsafe_allow_html=True)

# ── Helpers ────────────────────────────────────────────────────────────────

def priority_badge(p: str) -> str:
    return f'<span class="badge badge-{p}">{p}</span>'

def route_badge(r: str) -> str:
    label = {"AUTO_RESOLVE": "Auto", "REVIEW": "Review", "ESCALATE": "Escalate"}.get(r, r)
    return f'<span class="badge route-{r}">{label}</span>'

def sla_badge(label: str) -> str:
    key = label.replace(" ", "_")
    return f'<span class="badge sla-{key}">{label}</span>'

def conf_bar(score: float, color: str = "#3b82f6") -> str:
    pct = int(score * 100)
    return (
        f'<div class="conf-bar-wrap">'
        f'<div class="conf-bar" style="width:{pct}%;background:{color}"></div>'
        f'</div><small>{pct}%</small>'
    )

def _status_color(status: str) -> str:
    return {
        "OPEN": "🔵", "IN_REVIEW": "🟡", "ESCALATED": "🔴",
        "AUTO_RESOLVED": "🟢", "RESOLVED": "✅", "ON_HOLD": "⏸️",
    }.get(status, "⚪")

# ── Sidebar ────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("🎫 SupportOps")
    st.caption("Intelligent Customer Support System")
    st.divider()

    page = st.radio(
        "Navigate",
        ["📥 Process Queries", "🎫 Ticket Queue", "🔍 Ticket Detail",
         "👤 Human Review", "📊 Analytics", "📋 Audit Log"],
        label_visibility="collapsed",
    )

    st.divider()
    if st.button("🔄 Refresh data", use_container_width=True):
        st.rerun()

    tickets = get_all_tickets()
    open_count  = sum(1 for t in tickets if t["status"] == "OPEN")
    esc_count   = sum(1 for t in tickets if t["status"] == "ESCALATED")
    rev_count   = sum(1 for t in tickets if t["status"] == "IN_REVIEW")
    overdue     = get_overdue_tickets(tickets)

    st.markdown("**Live Queue**")
    c1, c2 = st.columns(2)
    c1.metric("Open",      open_count)
    c2.metric("Escalated", esc_count)
    c3, c4 = st.columns(2)
    c3.metric("In Review", rev_count)
    c4.metric("⚠️ Overdue", len(overdue))

# ── Page: Process Queries ──────────────────────────────────────────────────

if page == "📥 Process Queries":
    st.title("📥 Process Customer Queries")
    st.markdown("Upload a CSV file or use the bundled sample dataset to run the full pipeline.")

    tab_upload, tab_sample = st.tabs(["Upload CSV", "Use Sample Dataset"])

    with tab_upload:
        uploaded = st.file_uploader(
            "Upload customer_queries.csv",
            type=["csv"],
            help="Must have columns: query_id, customer_id, query_text, created_at"
        )
        if uploaded:
            with open("_uploaded_queries.csv", "wb") as f:
                f.write(uploaded.read())
            if st.button("▶ Run Pipeline", type="primary"):
                with st.spinner("Processing queries…"):
                    results, valid, rejected = process_queries("_uploaded_queries.csv")
                st.session_state["last_results"] = results
                st.session_state["last_rejected"] = rejected
                st.success(f"Processed {len(results)} queries ({len(rejected)} rejected)")
                st.rerun()

    with tab_sample:
        st.info("Uses the bundled `customer_queries.csv` (18 valid + 2 invalid records).")
        if st.button("▶ Run Pipeline on Sample Data", type="primary"):
            with st.spinner("Processing queries…"):
                results, valid, rejected = process_queries("customer_queries.csv")
            st.session_state["last_results"] = results
            st.session_state["last_rejected"] = rejected
            st.success(f"✓ {len(results)} processed | ✗ {len(rejected)} rejected")
            st.rerun()

    # Show last run results
    if "last_results" in st.session_state:
        results = st.session_state["last_results"]
        rejected = st.session_state.get("last_rejected", [])

        st.divider()
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Processed", len(results))
        col2.metric("Rejected",  len(rejected))
        col3.metric("Escalated", sum(1 for r in results if r["route"] == "ESCALATE"))
        col4.metric("Auto-Resolved", sum(1 for r in results if r["route"] == "AUTO_RESOLVE"))

        st.subheader("Processing Results")
        rows = []
        for r in results:
            clf = r["classification"]
            res = r["resolution"]
            rows.append({
                "Ticket": r["ticket_id"],
                "Query": r["query_id"],
                "Intent": clf["intent"],
                "Priority": clf["priority"],
                "Route": r["route"],
                "TF-IDF": f"{res['tfidf_score']:.2f}",
                "Baseline": f"{res['baseline_score']:.2f}",
                "Article": res["article_id"] or "—",
                "Status": r["status"],
            })
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)

        if rejected:
            st.subheader("⚠️ Rejected Records")
            rej_rows = [
                {"Query ID": item["record"].get("query_id", ""),
                 "Reason": "; ".join(item["errors"])}
                for item in rejected
            ]
            st.dataframe(pd.DataFrame(rej_rows), use_container_width=True, hide_index=True)

# ── Page: Ticket Queue ─────────────────────────────────────────────────────

elif page == "🎫 Ticket Queue":
    st.title("🎫 Ticket Queue")

    tickets = get_all_tickets()
    if not tickets:
        st.info("No tickets yet. Run the pipeline from '📥 Process Queries' first.")
        st.stop()

    # Filters
    col1, col2, col3 = st.columns(3)
    status_filter   = col1.multiselect("Status", ["OPEN","IN_REVIEW","ESCALATED",
                                                   "AUTO_RESOLVED","RESOLVED","ON_HOLD"],
                                        default=["OPEN","IN_REVIEW","ESCALATED"])
    priority_filter = col2.multiselect("Priority", ["P1","P2","P3","P4"],
                                        default=["P1","P2","P3","P4"])
    route_filter    = col3.multiselect("Route", ["ESCALATE","REVIEW","AUTO_RESOLVE"],
                                        default=["ESCALATE","REVIEW","AUTO_RESOLVE"])

    filtered = [
        t for t in tickets
        if t["status"] in status_filter
        and t["priority"] in priority_filter
        and t["route"] in route_filter
    ]

    st.caption(f"Showing {len(filtered)} of {len(tickets)} tickets")

    for t in filtered:
        sla = check_sla_status(t)
        with st.container():
            c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 2])
            c1.markdown(f"**{t['ticket_id']}** — {t['query_id']}")
            c2.markdown(priority_badge(t["priority"]), unsafe_allow_html=True)
            c3.markdown(route_badge(t["route"]), unsafe_allow_html=True)
            c4.markdown(f"{_status_color(t['status'])} {t['status']}")

            sla_label = sla["sla_label"]
            hrs = sla["hours_remaining"]
            sla_str = f"{hrs:.1f}h" if hrs is not None else "—"
            c5.markdown(
                sla_badge(sla_label) + f" &nbsp; {sla_str}",
                unsafe_allow_html=True,
            )

            st.caption(f"  {t['intent']} · {t['assigned_team']} · {t['query_text'][:90]}…")
            st.divider()

# ── Page: Ticket Detail ────────────────────────────────────────────────────

elif page == "🔍 Ticket Detail":
    st.title("🔍 Ticket Detail")

    tickets = get_all_tickets()
    if not tickets:
        st.info("No tickets found. Run the pipeline first.")
        st.stop()

    ticket_ids = [t["ticket_id"] for t in tickets]
    selected_id = st.selectbox("Select Ticket", ticket_ids)
    t = get_ticket(selected_id)
    if not t:
        st.error("Ticket not found.")
        st.stop()

    sla = check_sla_status(t)

    # Header row
    col1, col2, col3, col4 = st.columns(4)
    col1.markdown(f"### {t['ticket_id']}")
    col2.markdown(priority_badge(t["priority"]), unsafe_allow_html=True)
    col3.markdown(route_badge(t["route"]), unsafe_allow_html=True)
    col4.markdown(f"{_status_color(t['status'])} **{t['status']}**")

    st.divider()

    # Two-column layout
    left, right = st.columns([3, 2])

    with left:
        st.subheader("Customer Query")
        st.info(t["query_text"])

        st.subheader("🧠 Decision Trace")
        trace = f"""
Query ID      : {t['query_id']}
Intent        : {t['intent']}
Complexity    : {t['complexity']}
Priority      : {t['priority']}
Matched Rule  : (see classifier.py)

Route         : {t['route']}
Reason        : {t['route_reason']}

KB Article    : {t['article_id'] or 'None found'}
Article Title : {t['article_title'] or '—'}
Confidence    : {t['confidence']:.2%} (TF-IDF retrieval)

Assigned Team : {t['assigned_team']}
SLA Deadline  : {t['sla_deadline']}
SLA Status    : {sla['sla_label']}
        """.strip()
        st.code(trace, language="")

        st.subheader("📝 Proposed Response")
        st.markdown(t["proposed_response"])

    with right:
        st.subheader("SLA Status")
        hrs = sla["hours_remaining"]
        if hrs is not None:
            pct = max(0, min(1, hrs / 72))
            color = "#ef4444" if sla["is_breached"] else ("#f59e0b" if hrs < 1 else "#22c55e")
            st.markdown(conf_bar(pct, color), unsafe_allow_html=True)
            st.caption(f"{abs(hrs):.1f}h {'overdue' if sla['is_breached'] else 'remaining'}")

        st.subheader("Reviewer Decision")
        if t.get("reviewer_action"):
            st.success(f"**{t['reviewer_action']}**")
            if t.get("reviewer_note"):
                st.caption(t["reviewer_note"])
        else:
            st.caption("No reviewer action yet.")

        st.subheader("Ticket History")
        history = get_ticket_history(selected_id)
        for h in history:
            st.markdown(
                f"- `{h['changed_at'][:19]}` **{h['actor']}**: "
                f"{h['from_status'] or '–'} → {h['to_status']}  \n"
                f"  _{h['note']}_"
            )

# ── Page: Human Review ─────────────────────────────────────────────────────

elif page == "👤 Human Review":
    st.title("👤 Human Review Queue")
    st.markdown("Review escalated and flagged tickets. Approve, edit, hold, or escalate.")

    tickets = get_all_tickets()
    review_tickets = [
        t for t in tickets
        if t["status"] in ("IN_REVIEW", "ESCALATED", "ON_HOLD")
    ]

    if not review_tickets:
        st.success("✅ No tickets awaiting review.")
        st.stop()

    for t in review_tickets:
        sla = check_sla_status(t)
        with st.expander(
            f"{_status_color(t['status'])} {t['ticket_id']} — "
            f"{t['priority']} — {t['intent']} — {t['query_text'][:60]}…",
            expanded=(t["priority"] in ("P1", "P2")),
        ):
            col_l, col_r = st.columns([3, 2])

            with col_l:
                st.markdown("**Customer Query**")
                st.info(t["query_text"])

                st.markdown("**Route Reason**")
                st.markdown(
                    f'<div class="trace-box">{t["route_reason"]}</div>',
                    unsafe_allow_html=True,
                )

                st.markdown("**KB Article**")
                if t["article_title"]:
                    st.markdown(f"📄 `{t['article_id']}` — {t['article_title']}")
                    st.caption(f"Confidence: {t['confidence']:.0%}")
                else:
                    st.warning("No matching KB article found.")

                st.markdown("**Proposed Response**")
                edited_response = st.text_area(
                    "Edit before approving (optional)",
                    value=t["proposed_response"],
                    height=150,
                    key=f"resp_{t['ticket_id']}",
                )

            with col_r:
                st.markdown("**Priority**")
                st.markdown(priority_badge(t["priority"]), unsafe_allow_html=True)

                st.markdown("**SLA**")
                hrs = sla["hours_remaining"]
                if hrs is not None:
                    st.markdown(sla_badge(sla["sla_label"]), unsafe_allow_html=True)
                    st.caption(f"{abs(hrs):.1f}h {'overdue' if sla['is_breached'] else 'remaining'}")

                st.markdown("**Assigned Team**")
                st.caption(t["assigned_team"])

                reviewer_note = st.text_input(
                    "Reviewer note",
                    placeholder="Optional note…",
                    key=f"note_{t['ticket_id']}",
                )

                st.markdown("**Actions**")
                b1, b2 = st.columns(2)
                b3, b4 = st.columns(2)

                if b1.button("✅ Approve", key=f"approve_{t['ticket_id']}", use_container_width=True):
                    save_reviewer_action(t["ticket_id"], "APPROVED", reviewer_note, edited_response)
                    transition_status(t["ticket_id"], STATUS_RESOLVED,
                                      actor="reviewer", note=reviewer_note or "Approved by reviewer")
                    log_event("REVIEWER_ACTION", "APPROVED", ticket_id=t["ticket_id"],
                              actor="reviewer", new_value="RESOLVED")
                    st.success("Approved and resolved!")
                    st.rerun()

                if b2.button("⬆ Escalate", key=f"esc_{t['ticket_id']}", use_container_width=True,
                             type="secondary"):
                    save_reviewer_action(t["ticket_id"], "ESCALATED", reviewer_note)
                    if t["status"] != "ESCALATED":
                        transition_status(t["ticket_id"], STATUS_ESCALATED,
                                          actor="reviewer", note=reviewer_note or "Escalated by reviewer")
                    log_event("REVIEWER_ACTION", "ESCALATED", ticket_id=t["ticket_id"], actor="reviewer")
                    st.warning("Escalated!")
                    st.rerun()

                if b3.button("⏸ Hold", key=f"hold_{t['ticket_id']}", use_container_width=True):
                    save_reviewer_action(t["ticket_id"], "ON_HOLD", reviewer_note)
                    if t["status"] not in ("ON_HOLD",):
                        transition_status(t["ticket_id"], STATUS_ON_HOLD,
                                          actor="reviewer", note=reviewer_note or "Put on hold")
                    log_event("REVIEWER_ACTION", "ON_HOLD", ticket_id=t["ticket_id"], actor="reviewer")
                    st.info("Ticket placed on hold.")
                    st.rerun()

                if b4.button("📨 Request Info", key=f"req_{t['ticket_id']}", use_container_width=True):
                    save_reviewer_action(t["ticket_id"], "REQUEST_INFO", reviewer_note)
                    log_event("REVIEWER_ACTION", "REQUEST_INFO",
                              ticket_id=t["ticket_id"], actor="reviewer",
                              detail=reviewer_note)
                    st.info("Information request logged.")
                    st.rerun()

# ── Page: Analytics ────────────────────────────────────────────────────────

elif page == "📊 Analytics":
    st.title("📊 Evaluation & SLA Analytics")

    tickets = get_all_tickets()
    if not tickets:
        st.info("No tickets yet. Run the pipeline first.")
        st.stop()

    df = pd.DataFrame(tickets)

    # ── Top KPIs ───────────────────────────────────────────────────────────
    total = len(df)
    auto_res  = len(df[df["route"] == "AUTO_RESOLVE"])
    escalated = len(df[df["route"] == "ESCALATE"])
    review    = len(df[df["route"] == "REVIEW"])
    resolved  = len(df[df["status"].isin(["RESOLVED", "AUTO_RESOLVED"])])
    overdue   = len(get_overdue_tickets(tickets))

    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Total Tickets",   total)
    k2.metric("Auto-Resolved",   auto_res,  f"{auto_res/total:.0%}")
    k3.metric("Escalated",       escalated, f"{escalated/total:.0%}")
    k4.metric("In Review",       review,    f"{review/total:.0%}")
    k5.metric("Resolved",        resolved,  f"{resolved/total:.0%}")
    k6.metric("⚠️ SLA Breached", overdue)

    st.divider()

    # ── Charts row 1 ──────────────────────────────────────────────────────
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Route Distribution")
        route_counts = df["route"].value_counts()
        st.bar_chart(route_counts)

    with col2:
        st.subheader("Priority Distribution")
        pri_counts = df["priority"].value_counts().sort_index()
        st.bar_chart(pri_counts)

    # ── Charts row 2 ──────────────────────────────────────────────────────
    col3, col4 = st.columns(2)

    with col3:
        st.subheader("Intent Distribution")
        intent_counts = df["intent"].value_counts()
        st.bar_chart(intent_counts)

    with col4:
        st.subheader("Status Distribution")
        status_counts = df["status"].value_counts()
        st.bar_chart(status_counts)

    # ── Retrieval comparison: TF-IDF vs Baseline ───────────────────────────
    st.divider()
    st.subheader("🔬 TF-IDF vs Keyword Baseline Retrieval (per ticket)")

    if "confidence" in df.columns:
        conf_df = df[["ticket_id","query_id","intent","confidence"]].copy()
        conf_df.columns = ["Ticket","Query","Intent","TF-IDF Score"]
        conf_df = conf_df.sort_values("TF-IDF Score", ascending=False)
        conf_df["TF-IDF Score"] = conf_df["TF-IDF Score"].round(3)
        st.dataframe(conf_df, use_container_width=True, hide_index=True)

        avg_conf = df["confidence"].mean()
        st.info(f"Average TF-IDF retrieval score: **{avg_conf:.2%}**")

    # ── Notification retry analysis ────────────────────────────────────────
    st.divider()
    st.subheader("📬 Notification Retry Analysis")
    notif_log = "notification_log.csv"
    if os.path.exists(notif_log):
        ndf = pd.read_csv(notif_log)
        retry_summary = ndf.groupby("ticket_id")["attempt"].max().reset_index()
        retry_summary.columns = ["Ticket ID", "Max Attempts"]
        multi_attempt = retry_summary[retry_summary["Max Attempts"] > 1]
        st.metric("Tickets needing retries", len(multi_attempt))
        if not ndf.empty:
            status_counts_n = ndf.groupby(["attempt", "status"]).size().unstack(fill_value=0)
            st.dataframe(status_counts_n, use_container_width=True)
    else:
        st.caption("notification_log.csv not found – run pipeline first.")

    # ── SLA compliance table ───────────────────────────────────────────────
    st.divider()
    st.subheader("⏰ SLA Compliance by Ticket")
    sla_rows = []
    for t in tickets:
        sla = check_sla_status(t)
        sla_rows.append({
            "Ticket": t["ticket_id"],
            "Priority": t["priority"],
            "Status": t["status"],
            "SLA Status": sla["sla_label"],
            "Hours Remaining": f"{sla['hours_remaining']:.1f}" if sla["hours_remaining"] is not None else "—",
        })
    sla_df = pd.DataFrame(sla_rows)
    st.dataframe(sla_df, use_container_width=True, hide_index=True)

# ── Page: Audit Log ────────────────────────────────────────────────────────

elif page == "📋 Audit Log":
    st.title("📋 Audit Log")

    audit_path = "audit_log.csv"
    if not os.path.exists(audit_path):
        st.info("Audit log not generated yet. Run the pipeline first.")
        st.stop()

    adf = pd.read_csv(audit_path)
    st.metric("Total audit events", len(adf))

    event_filter = st.multiselect(
        "Filter by event type",
        sorted(adf["event_type"].unique().tolist()),
        default=sorted(adf["event_type"].unique().tolist()),
    )
    filtered_adf = adf[adf["event_type"].isin(event_filter)]

    st.dataframe(
        filtered_adf.sort_values("timestamp", ascending=False),
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "⬇ Download Audit Log",
        data=open(audit_path, "rb").read(),
        file_name="audit_log.csv",
        mime="text/csv",
    )
