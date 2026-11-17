# Recruitment Workflow — `uv` project

A Streamlit recruitment workflow lab implementation with explainable scoring, CSV ingestion, validation, duplicate quarantine, human review, notification drafts, SQLite audit events, a scoring rule simulator, quality report, and tests.

## Run the app

Requires Python 3.10+ and `uv`.

```powershell
uv sync
uv run streamlit run app.py
```

Run tests:

```powershell
uv run pytest
uv run ruff check .
```

The bundled `data/candidates.csv` is fictional, has 150 records, and includes deliberate edge cases so the app works immediately.

## Optional: use the selected Hugging Face dataset

Dataset: https://huggingface.co/datasets/uhfew/recruitment_data

```powershell
uv add datasets
uv run python scripts/import_huggingface_dataset.py
```

This optional importer writes `data/candidates.csv`. Back up the bundled dataset first if you want to keep it.

### Mapping caveat

The importer derives:
- skills score from overlap between required and applicant keywords;
- experience score from years of experience using a capped, documented mapping;
- assessment score as a synthetic proxy derived from the other two because the source does not contain a real technical assessment score.

These are demonstration values, not actual assessment results. The source's historical outcome is retained for context only and is not used by the scoring engine.

## Project structure

- `app.py`: Streamlit interface.
- `recruitment_workflow.py`: validation, scoring, routing, notifications, SQLite audit, review.
- `notifications.py`: notification draft interface.
- `rules.json`: configurable scoring rules.
- `data/candidates.csv`: bundled synthetic dataset.
- `data/test_edge_cases.csv`: small boundary/error fixture.
- `scripts/import_huggingface_dataset.py`: optional source dataset importer.
- `tests/test_recruitment.py`: automated tests.
- `reports/`: generated reports and quarantined records.

## Review and notification safety

No real emails are sent. `SENT_SIMULATED` means the reviewer approved a simulated dispatch. For lab demonstration only, reviewer identifiers beginning with `HR_` pass the simple authorization gate; this is not production authentication.

Audit events are appended to SQLite. Reprocessing updates the current application projection keyed by candidate ID but appends a new event. Duplicate IDs inside one input batch are quarantined.

## Responsible use

Use fictional data only. Score documented, job-related criteria. Rules and thresholds are illustrative. Counterfactual checks and synthetic data do not establish real-world fairness or hiring validity.
