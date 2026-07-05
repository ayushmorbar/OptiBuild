# Capstone Video Assets & Capture Guide

Checklist of demonstrable artifacts for the capstone video, mapped to the six concepts
(`specs/architecture.md` §10). Each segment lists the exact command(s) to run on camera
(or to capture beforehand) and what to show.

## Segment 1 — Multi-agent system (ADK) — concept 1

**Show:** the deployed chat UI (or `uv run adk web` locally), a full conversation.

```bash
uv run adk web       # local — or open the Cloud Run URL (see below)
```

Prompt to use on camera:

> Build me a quiet gaming PC under $1500 with at least 32GB of RAM

Point out in the ADK event pane: the `safety_guard` sub-agent call, then the single
consolidated `optimize_request` tool call, then the final table (selections + derived
values + objective report).

## Segment 2 — MCP server — concept 2

**Show:** the 7 deterministic tools and the stdio server.

```bash
# Tool registration lives in app/mcp_server/server.py (7 @mcp.tool functions)
uv run python -m app.mcp_server   # starts the FastMCP stdio server (Ctrl+C to stop)
uv run pytest tests/unit/test_mcp_server.py tests/integration/test_mcp_pipeline.py -q
```

## Segment 3 — Security — concept 3

**Show:** hostile inputs rejected by design (zero code execution).

```bash
uv run python scripts/run_security_demo.py
```

Highlights to narrate: hostile `expr` (`os.system`, dunders, calls) rejected with
reasons; ">90% row drop" batch revert; prompt-injection treated as data; PII redaction
(case 23 of the eval set: credit card + SSN → `[REDACTED ...]`).

## Segment 4 — Eval suite (agents-cli) — concept 4

**Show:** the dataset, one `generate`/`grade` run, and the scores table.

```bash
# 23 cases across happy / budget-edge / constraints / ambiguous / guardrail classes
uv run python -c "import json; d=json.load(open('tests/eval/datasets/basic-dataset.json')); print(len(d['eval_cases']), 'cases')"
agents-cli eval grade --traces artifacts/traces/traces_baseline.json --config tests/eval/eval_config.yaml --project <PROJECT_ID> --output artifacts/eval/baseline/
```

Scores: see `docs/eval-report.md` (baseline → final per metric).

## Segment 5 — Antigravity — concept 5

**Show:** the development workflow in the IDE (no code artifact required):
agentic session, terminal logs, the spec-driven loop (`specs/architecture.md` →
implementation → tests green).

## Segment 6 — Deployability — concept 6

**Show:** the live Cloud Run service.

```bash
# Deployed URL (fill in after deploy):
#   https://<CLOUD_RUN_URL>
curl -s https://<CLOUD_RUN_URL>/list-apps
# Then open the UI in a browser and run the Segment-1 prompt against the LIVE service.
```

## Bonus segment — Domain-agnosticism (differentiator)

**Show:** the same engine optimizing a *meal plan* — zero code change, different data.

```bash
# PowerShell
$env:GAUSS_DATA_DIR = "tests/fixtures/toy-pack"; uv run adk web
```

Prompt:

> cheapest full meal under $10

Point out `trace.category_resolution` when phrasing it as "main dish" instead of
"protein" — metadata search maps user vocabulary onto the catalog.

---

## Capture inventory (tick as recorded)

- [ ] ADK web conversation (local or deployed) — full happy path
- [ ] Security demo terminal output
- [ ] Eval grade scores table (baseline + final)
- [ ] Cloud Run console + live URL responding
- [ ] Toy-pack domain switch
- [ ] Antigravity IDE workflow footage
