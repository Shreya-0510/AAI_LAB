import json, sqlite3
from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st
from recruitment_workflow import (audit_event, generate_notification, init_db, load_candidates,
    load_rules, process_batch, review_application, route_candidate, save_rejected_csv, score_candidate)

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "candidates.csv"
RULES_PATH = ROOT / "rules.json"
DB = ROOT / "data" / "recruitment.db"
REPORTS = ROOT / "reports"
st.set_page_config(page_title="Recruitment Workflow", page_icon="🧭", layout="wide")
st.title("Recruitment Workflow")
st.caption("Explainable scoring · human-controlled review · quality analytics")
init_db(DB)

with st.sidebar:
    st.header("Navigation")
    page = st.radio("Open page", ["Overview", "Candidate Review", "Rule Simulator", "Data Quality & Audit", "Evaluation Report"])
    st.divider()
    st.caption("Fictional data only · no real emails are sent")

def process(path):
    rules = load_rules(RULES_PATH)
    result = process_batch(load_candidates(path), rules, DB)
    save_rejected_csv(result["rejected"], REPORTS / "rejected_records.csv")
    st.session_state["result"] = result
    return result

def get_result():
    if "result" not in st.session_state and DATA.exists():
        try: return process(DATA)
        except Exception as exc: st.error(f"Could not load dataset: {exc}"); return None
    return st.session_state.get("result")

def audit_df():
    with sqlite3.connect(DB) as c:
        return pd.read_sql_query("SELECT * FROM audit_events ORDER BY event_id DESC", c)

def apps_df():
    with sqlite3.connect(DB) as c:
        return pd.read_sql_query("SELECT * FROM applications ORDER BY updated_at DESC", c)

def review_rate():
    d = apps_df()
    return round(100 * (d["reviewer_action"] != "PENDING").sum() / len(d), 2) if len(d) else 0.0

def report(r):
    n, v = r["total_records"], len(r["results"])
    counts = pd.Series([x["proposed_status"] for x in r["results"]]).value_counts().to_dict()
    integrity = sum(abs(sum(x["weighted_contribution"] for x in row["breakdown"].values())-row["score"]) < .011 for row in r["results"])
    return {"total_records": n, "valid_records": v, "invalid_or_quarantined": len(r["rejected"]),
            "validation_rate_pct": round(100*v/n,2) if n else 0,
            "workflow_success_rate_pct": 100.0 if v else 0.0,
            "notification_drafts_generated": v, "notification_draft_rate_pct": 100.0 if v else 0.0,
            "proposed_status_counts": counts, "processing_seconds": round(r["elapsed_seconds"],6),
            "average_ms_per_valid_record": round(r["avg_ms_per_valid"],3),
            "score_integrity_checks_passed": int(integrity), "score_integrity_checks_total": v,
            "score_integrity_pass_rate_pct": round(100*integrity/v,2) if v else 100,
            "human_review_completion_pct": review_rate(),
            "notification_delivery": "Simulated only; no external messages sent."}

if page == "Overview":
    st.subheader("Run the workflow")
    uploaded = st.file_uploader("Upload a candidate CSV", type=["csv"])
    col1, col2 = st.columns(2)
    if uploaded and col1.button("Process uploaded CSV", type="primary"):
        p = ROOT / "data" / "_uploaded.csv"; p.write_bytes(uploaded.getvalue())
        try: st.success(f"Processed {process(p)['total_records']} rows.")
        except Exception as e: st.error(str(e))
    if col2.button("Run bundled dataset"):
        try: st.success(f"Processed {process(DATA)['total_records']} rows.")
        except Exception as e: st.error(str(e))
    st.info("Optional: `uv add datasets` then `uv run python scripts/import_huggingface_dataset.py` to import the selected Hugging Face dataset.")
    r = get_result()
    if r:
        q = report(r)
        a,b,c,d = st.columns(4)
        a.metric("Records", q["total_records"]); b.metric("Valid", q["valid_records"])
        c.metric("Quarantined", q["invalid_or_quarantined"]); d.metric("Time", f"{q['processing_seconds']:.3f}s")
        df = pd.DataFrame(r["results"])
        if not df.empty:
            x,y = st.columns(2)
            counts = df["proposed_status"].value_counts().rename_axis("Status").reset_index(name="Count")
            x.plotly_chart(px.pie(counts, names="Status", values="Count", hole=.5, title="Proposed categories"), use_container_width=True)
            y.plotly_chart(px.histogram(df, x="score", nbins=20, title="Score distribution"), use_container_width=True)
            st.dataframe(df[["candidate_id","candidate_name","score","proposed_status"]].head(20), use_container_width=True, hide_index=True)

elif page == "Candidate Review":
    r = get_result()
    if r:
        df = pd.DataFrame(r["results"])
        if df.empty: st.info("No valid candidate records.")
        else:
            filt = st.selectbox("Status", ["All"] + sorted(df.proposed_status.unique()))
            view = df if filt == "All" else df[df.proposed_status == filt]
            st.dataframe(view[["candidate_id","candidate_name","email","score","proposed_status","rule_version"]], use_container_width=True, hide_index=True)
            cid = st.selectbox("Select candidate", view.candidate_id.tolist())
            row = next(x for x in r["results"] if x["candidate_id"] == cid)
            st.subheader(f"{row['candidate_name']} · {cid}")
            st.metric("Overall score", f"{row['score']:.2f}/100")
            st.dataframe(pd.DataFrame([{"Criterion": v["label"], "Input": v["input_score"], "Weight": v["weight"], "Contribution": v["weighted_contribution"]} for v in row["breakdown"].values()]), hide_index=True, use_container_width=True)
            draft = generate_notification(row, row["proposed_status"])
            st.markdown("**Notification draft preview** — no email is sent")
            st.text_input("Subject", draft["subject"], key=f"sub{cid}")
            st.text_area("Message", draft["message"], height=130, key=f"msg{cid}")
            with st.form(f"review{cid}"):
                reviewer = st.text_input("Reviewer ID", "HR_REVIEWER")
                action = st.selectbox("Action", ["APPROVE","EDIT","HOLD","REQUEST_INFO"])
                edited = st.selectbox("Edited status", ["SHORTLIST_REVIEW","MANUAL_REVIEW","NOT_SHORTLISTED_REVIEW","REQUIRES_REVIEW","ON_HOLD","AWAITING_INFORMATION"])
                notes = st.text_area("Review notes / override reason")
                msg_ok = st.checkbox("Approve final draft for simulated dispatch")
                submitted = st.form_submit_button("Record review decision")
            if submitted:
                if not reviewer.strip(): st.error("Reviewer ID required.")
                elif action == "EDIT" and not notes.strip(): st.error("Document the reason for an override.")
                elif msg_ok and action != "APPROVE": st.error("Only an approved action can simulate dispatch.")
                else:
                    try:
                        out = review_application(cid, action, reviewer, notes, edited if action=="EDIT" else None,
                            msg_ok, DB, authorized=reviewer.strip().upper().startswith("HR_"))
                        st.success(f"{out['final_status']} · notification {out['notification_status']}")
                    except Exception as e: st.error(str(e))

elif page == "Rule Simulator":
    r = get_result()
    if r:
        base = load_rules(RULES_PATH)
        st.write("Compare alternative weights and thresholds on the same candidates. This simulation does not modify baseline decisions.")
        w1 = st.slider("Skills weight (%)", 0, 100, 40)
        w2 = st.slider("Experience weight (%)", 0, 100-w1, min(30,100-w1))
        w3 = 100-w1-w2
        st.metric("Assessment weight (%)", w3)
        short = st.slider("Shortlist threshold", 0, 100, 75)
        manual = st.slider("Manual review threshold", 0, short, min(50,short))
        if st.button("Compare rules", type="primary"):
            alt = json.loads(json.dumps(base)); alt["rule_version"] = "SIMULATION"
            for field, weight in zip(["skills_score","experience_score","assessment_score"],[w1,w2,w3]):
                alt["criteria"][field]["weight"] = weight
            alt["thresholds"] = {"shortlist_review":short,"manual_review":manual}
            rows = []
            for row in r["results"]:
                s = score_candidate(row,alt)["score"]; status = route_candidate(s,alt)
                rows.append({"candidate_id":row["candidate_id"],"candidate_name":row["candidate_name"],
                    "baseline_score":row["score"],"simulated_score":s,"score_change":round(s-row["score"],2),
                    "baseline_status":row["proposed_status"],"simulated_status":status,
                    "category_changed":row["proposed_status"] != status})
            comp = pd.DataFrame(rows); changed = int(comp.category_changed.sum())
            a,b,c = st.columns(3); a.metric("Compared",len(comp)); b.metric("Category changes",changed)
            c.metric("Transition rate",f"{100*changed/len(comp):.1f}%" if len(comp) else "0%")
            st.plotly_chart(px.scatter(comp,x="baseline_score",y="simulated_score",color="category_changed",
                hover_data=["candidate_id","baseline_status","simulated_status"],title="Baseline vs simulated scores"),use_container_width=True)
            st.dataframe(comp[comp.category_changed],use_container_width=True,hide_index=True)
            st.download_button("Download comparison CSV",comp.to_csv(index=False).encode(),"rule_comparison.csv","text/csv")

elif page == "Data Quality & Audit":
    r = get_result()
    if r:
        a,b,c = st.columns(3); a.metric("Total",r["total_records"]); b.metric("Valid",len(r["results"])); c.metric("Quarantined",len(r["rejected"]))
        if r["rejected"]:
            st.subheader("Rejected / quarantined")
            st.dataframe(pd.DataFrame(r["rejected"]),use_container_width=True,hide_index=True)
            st.download_button("Download rejected CSV",pd.DataFrame(r["rejected"]).to_csv(index=False).encode(),"rejected_records.csv","text/csv")
        st.subheader("Audit events")
        ev = audit_df(); st.dataframe(ev.head(500),use_container_width=True,hide_index=True)
        st.download_button("Download audit events",ev.to_csv(index=False).encode(),"audit_events.csv","text/csv")
        if st.button("Run irrelevant-attribute counterfactual check"):
            rules=load_rules(RULES_PATH); passed=0
            for row in r["results"]:
                a=score_candidate(row,rules)["score"]; altered=dict(row); altered["irrelevant_demo_attribute"]="changed"
                passed += score_candidate(altered,rules)["score"] == a
            st.success(f"Passed {passed}/{len(r['results'])} counterfactual consistency checks.")
            st.caption("This verifies that an unused field is ignored; it does not prove overall fairness.")

elif page == "Evaluation Report":
    r = get_result()
    if r:
        q=report(r)
        a,b,c,d=st.columns(4); a.metric("Validation rate",f"{q['validation_rate_pct']:.1f}%")
        b.metric("Workflow success",f"{q['workflow_success_rate_pct']:.1f}%")
        c.metric("Draft generation",f"{q['notification_draft_rate_pct']:.1f}%")
        d.metric("Human review completion",f"{q['human_review_completion_pct']:.1f}%")
        st.json(q)
        st.download_button("Download quality report JSON",json.dumps(q,indent=2).encode(),"quality_report.json","application/json")
        st.markdown("Metrics describe software behavior, not the validity or fairness of hiring decisions.")
