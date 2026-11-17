# DART — Dependency-Aware Regression Testing

DART is a research-oriented prototype for evaluating whether LLM-assisted, dependency-aware regression-test selection can reduce test execution effort while preserving regression-detection effectiveness.

## What is implemented

- FastMCP server exposing repository, diff, dependency, test discovery, plan validation, test execution, results, and report tools.
- MCP client using `ClientSession` over stdio and dynamic tool discovery.
- Groq-backed test-selection planner. If no API key is configured, the UI explicitly labels the fallback as **heuristic**, not LLM-generated.
- Three comparable strategies: full suite, LLM-only, and hybrid DART.
- Static Python import analysis and heuristic test-to-module mapping.
- Supervisor and policy validation before test execution.
- Timeouts, approved pytest target checks, output limits, run traces, JSON/CSV exports, and a Streamlit dashboard.
- A small demo repository so the project can be tried without selecting another repository.

## Important safety note

Running tests from a repository executes that repository's Python code. Only run tests from repositories you trust. DART avoids constructing shell commands from LLM output, restricts targets to discovered test files, applies a timeout, and requires an explicit execution action in the UI. These controls are **not a security sandbox**. Use a disposable container/VM for untrusted repositories.

## Requirements

- Python 3.12 (recommended)
- `uv`
- A Groq API key for LLM mode (optional for heuristic demo mode)
- Git is recommended for commit-range analysis

## Setup (VS Code terminal)

```powershell
uv python install 3.12
uv sync
Copy-Item .env.example .env
```

Edit `.env` and set `GROQ_API_KEY` and `GROQ_MODEL`. Keep `.env` private; it is ignored by Git.

Run tests:

```powershell
uv run pytest
```

Start the dashboard:

```powershell
uv run streamlit run app.py
```

The default repository is `sample_data/demo_repository`. You can enter another local Python repository path in the dashboard. The path must exist and contain Python files. For reproducible research, record the repository URL, commit hash, scenario ID, strategy, and repeated run number.

## MCP architecture

Streamlit workflow → MCP stdio client → dynamically discovered FastMCP tools → repository analysis / test execution → validated results → trace and report artifacts.

The MCP server is launched as a child process by the client. The client discovers tool schemas at runtime rather than hard-coding the server's available tools.

## Evaluation design

The three strategies are:

1. **Full suite:** run all discovered pytest test files.
2. **LLM-only:** use LLM-recommended test files, filtered through the same target validation and execution policy.
3. **Hybrid DART:** combine LLM recommendations with dependency/test mapping and supervisor validation.

Report at least:

- selected test files / total test files
- test-selection reduction percentage
- selection precision and recall, when expected relevant tests are supplied
- regression-detection rate, when controlled fault scenarios and known failing tests are supplied
- execution time and orchestration overhead
- failed/passed test counts, policy rejections, and workflow success

Do not conflate test-selection recall with regression-detection rate. A selected test can be relevant without detecting a particular defect. The demo repository is for functional demonstration; it is not sufficient by itself to establish research conclusions. Use multiple real repositories and controlled scenarios for a defensible evaluation.

## Project layout

```text
DART/
├── app.py
├── pages/
├── src/dart/
│   ├── config.py, schemas.py
│   ├── llm/                 # Groq provider and planner
│   ├── mcp_server/          # FastMCP server and tools
│   ├── mcp_client/          # stdio connection, discovery, invocation
│   ├── analysis/            # diff, dependency graph, selection strategies
│   ├── orchestration/       # supervisor, policy, scheduler, validation, recovery
│   ├── execution/           # approved pytest runner
│   ├── observability/       # traces and metrics
│   ├── evaluation/          # scoring and comparisons
│   └── reporting/           # JSON/CSV report export
├── tests/
├── benchmarks/
├── sample_data/demo_repository/
└── artifacts/
```

## Limitations to disclose in your report

- Static Python import analysis cannot resolve every dynamic import, plugin, reflection path, or runtime dependency.
- Test-to-module mapping is heuristic unless coverage data or explicit mappings are added.
- LLM output may omit relevant tests; record model ID and prompt/version.
- Local subprocess execution is not a hardened sandbox.
- A single demo run does not support claims about general effectiveness.
