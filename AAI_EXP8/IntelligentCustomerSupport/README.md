# Intelligent Customer Support System

A modular Python application implementing an intelligent customer support workflow with evidence-grounded retrieval, risk-aware escalation, and an explainable decision engine.

## Setup (using uv)

```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Navigate to the project
cd IntelligentCustomerSupport

# Create virtual environment and install dependencies
uv sync

# Run the CLI pipeline
uv run python app.py

# Launch the Streamlit dashboard
uv run streamlit run dashboard.py

# Run the test suite
uv run pytest test_support.py -v
```

## Project Structure

| File | Purpose |
|---|---|
| `app.py` | Core pipeline: ingest → classify → resolve → route → ticket → notify |
| `classifier.py` | Rule-based intent/priority/complexity classifier |
| `resolver.py` | TF-IDF + cosine similarity retrieval (vs keyword baseline) |
| `workflow_router.py` | Risk-aware routing with explicit decision traces |
| `ticket_manager.py` | SQLite-backed ticket lifecycle management |
| `notifications.py` | Mock notification service with retry logic |
| `sla_monitor.py` | SLA deadline calculation and breach detection |
| `audit_logger.py` | Append-only audit log (CSV) |
| `dashboard.py` | Streamlit operations dashboard |
| `test_support.py` | Full test suite (pytest) |

## Key Enhancements Over Baseline

1. **TF-IDF Retrieval** — cosine similarity against knowledge base articles; quantitatively compared against keyword baseline per-ticket
2. **Explainable Routing** — every routing decision produces a human-readable reason stored in the ticket and audit log
3. **Human-in-the-Loop Review Screen** — Approve / Escalate / Hold / Request Info actions with audit trail
4. **Adversarial Safety Tests** — prompt injection, security-hidden-in-billing, no-match scenarios
5. **Analytics Dashboard** — route distribution, SLA compliance, retrieval comparison, notification retries
