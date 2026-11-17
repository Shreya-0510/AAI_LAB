# ShopMind – Multi-Agent E-Commerce Shopping Assistant

Experiment 5: planner → router → parallel search agents → synchronizer → filter → comparison → ranking →
validator → supervisor → human approval, with tracing, retries, fallbacks, conflict resolution,
role-based tool access, adversarial tests and a sequential-vs-parallel benchmark.

## Run (uv)
```bash
uv sync
cp .env.example .env        # optional: add BESTBUY_API_KEY
uv run streamlit run app.py
```
Works with no keys: Best Buy is skipped → DummyJSON (live) → offline catalog.
