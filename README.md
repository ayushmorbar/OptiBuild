# OptiBuild — Domain-Agnostic Optimization Agent

OptiBuild turns a **free-form natural-language request** into a formal **Operations Research model** (decision variables, objectives, constraints), solves it with **CP-SAT** over a catalog of CSV datasets, and returns the optimal selection — with multi-objective ranking via **TOPSIS** when needed.

The engine contains **zero domain knowledge**: everything domain-specific lives in a swappable *dataset pack*. The bundled demo pack optimizes **PC builds** ("quiet gaming PC under $1500"), but the same code optimizes any selection problem (meal plans, portfolios, fleets…) just by pointing it at another pack.

Built with **Google ADK** (multi-agent), **FastMCP** (tool server), **OR-Tools CP-SAT** (solver), **pymcdm** (TOPSIS), and **Pydantic** (contracts). Capstone project for the *AI Agents Intensive* course.

---

## How it works

```
User request (chat)
   │
   ▼
Concierge root_agent (ADK, Gemini)          ← PII redaction + maturity check
   │  consolidated request → optimize_request tool
   ▼
Safety gate (deterministic LLM check)       ← imposed before the loop; REFUSED stops here
   ▼
Concierge Optimizer Loop (max 3 iterations)
   │  1. Modelization — 4 staged LLM extractions:
   │     decision variables → derived variables → objectives → constraints
   │  2. Pivot Schema (Pydantic) — the validated OR model
   │  3. Evaluator — deterministic completeness & coherence checks,
   │     then LLM judge (intent fidelity); failures → targeted REPAIR
   ▼
Solver pipeline (deterministic)
   │  category resolution (metadata search) → load CSVs → data gates
   │  → systematic cleaning → prefilter → CP-SAT → TOPSIS (if ≥2 objectives)
   ▼
Result: optimal selection + derived values + objective report + trace
```

Failure paths loop back with structured feedback: `MISSING_DATA` (a referenced column doesn't exist), `INFEASIBLE` (with relaxation suggestions), or `NEEDS_CLARIFICATION` (questions for the user after 3 failed iterations).

Full design docs live in [`specs/`](specs/): [`architecture.md`](specs/architecture.md) (authoritative), [`workflow-final.md`](specs/workflow-final.md) (as-built diagram), [`tasks.md`](specs/tasks.md) (implementation status).

---

## Requirements

- **Python ≥ 3.11** and **[uv](https://docs.astral.sh/uv/getting-started/installation/)**
- A **Gemini API key** ([AI Studio](https://aistudio.google.com/apikey)) — only for the LLM-driven entry points; the solver pipeline and most demos run fully offline

## Setup

```bash
git clone <repo-url> && cd optibuild
uv sync

# LLM credentials (only needed for chat / NL demos)
cp app/.env.example app/.env
# then edit app/.env and set GOOGLE_API_KEY
```

Verify the install:

```bash
uv run pytest          # 87 tests, no API key needed
uv run ruff check .
```

---

## Usage

### 1. Chat interface (full system, needs API key)

```bash
uv run adk web
```

Open the local URL, select the `app` agent, and ask e.g.:

> *"Build me a quiet gaming PC under $1500 with at least 32GB of RAM"*

The agent gathers your requirements, runs the full modelization → evaluation → solving loop, and presents the optimal build as a table with prices, totals, and a justification.

### 2. Demo scripts

| Script | LLM? | What it shows |
|---|---|---|
| `uv run python scripts/run_offline_demo.py` | ❌ | Full solver pipeline on a hand-built schema (8-category PC build, minimize price) |
| `uv run python scripts/run_solver_demo.py` | ❌ | Solver + A2A response contract on a small schema |
| `uv run python scripts/run_security_demo.py` | ❌ | Security layer: hostile expressions rejected, >90% row-drop reverted |
| `uv run python scripts/run_concierge_demo.py` | ✅ | Natural language → staged modelization → evaluator → solve |
| `uv run python scripts/run_concierge_oneshot_demo.py` | ✅ | Same, with the quota-friendly one-shot extraction path |

### 3. Switching domains (dataset packs)

The active pack is selected with the `GAUSS_DATA_DIR` environment variable (default: `data/pc-csv`):

> **Note — the `GAUSS_` prefix.** OptiBuild was originally released as *GAUSS*. The
> project has since been renamed, but every environment variable still uses the
> historical `GAUSS_` prefix (`GAUSS_DATA_DIR`, `GAUSS_EVAL_ENABLED`,
> `GAUSS_FAST_MODELIZATION`, `GAUSS_DYNAMIC_CLEAN`), as do the package name and the
> `gauss-solver` MCP server. These are internal identifiers — never user-facing — and
> are kept as-is so existing `.env` files, deployments, and CI configs keep working.

```bash
# PowerShell
$env:GAUSS_DATA_DIR = "tests/fixtures/toy-pack"; uv run pytest tests/integration/test_toy_pack_pipeline.py

# bash
GAUSS_DATA_DIR=tests/fixtures/toy-pack uv run pytest tests/integration/test_toy_pack_pipeline.py
```

`tests/fixtures/toy-pack` is a minimal **meal-plan** domain (cost column named `cost`, not `price`) proving the engine is domain-agnostic: same code, different data.

---

## Creating your own dataset pack

A pack is a directory containing one CSV per category plus a `metadata.json` catalog:

```
my-pack/
├── category-a.csv        # must have a 'name' column; one row per selectable item
├── category-b.csv
└── metadata.json
```

`metadata.json` — top-level fields are **optional** (absent → generic behavior):

```jsonc
{
  "version": "1.0",
  "domain": {                             // flavors the LLM prompts
    "name": "meal plan",
    "description": "Composing a meal from a protein and a side."
  },
  "required_categories": ["protein", "side"],   // evaluator completeness policy
  "primary_cost_column": "cost",                // implicit column, row-cap sort, cleaning rules
  "safety_notes": ["unsafe food-handling advice"],  // appended to guardrails
  "datasets": [
    {
      "file_name": "protein.csv",
      "category_key": "protein",
      "description": "Main protein dishes with cost and calories.",
      "synonyms": ["main dish", "entree"],        // powers category resolution
      "record_count": 5,
      "columns": {
        "name":     {"type": "str",   "required": true},
        "cost":     {"type": "float", "required": true, "unit": "USD"},
        "calories": {"type": "int",   "required": false, "unit": "kcal"}
      },
      "known_quirks": []
    }
  ]
}
```

Generate/refresh the `datasets` section from your CSVs (hand-authored and top-level fields are preserved):

```bash
uv run python scripts/gen_metadata.py --data-dir path/to/my-pack
```

Then point the system at it: `GAUSS_DATA_DIR=path/to/my-pack uv run adk web`.

**Category resolution:** users (and the LLM) don't need exact category keys — decision variables are matched against the catalog by search (exact key → synonym → fuzzy), and the mapping is recorded in the response `trace.category_resolution`.

---

## Security model

**No LLM output is ever executed as code** — zero `exec`/`eval` in the system:

- **Restricted formula grammar** — derived variables are declarations (`sum(a.cost, b.cost)`) compiled by deterministic code, never Python.
- **Allowlisted query expressions** — the only "code-like" LLM channel (pandas `query` strings) is token-gated (declared columns, literals, comparison/boolean ops only; no calls, no `@`, no attribute access) and evaluated with `engine="numexpr"`.
- **Closed cleaning vocabulary** — dynamic cleaning accepts only 4 declarative `CleanOp` types (strict Pydantic, `extra="forbid"`); ops can only reduce/normalize rows. Effect validation reverts any batch dropping >90% of a category.
- **Strict contracts everywhere** — every inter-component payload is a validated Pydantic model; raw user text travels only inside delimited `<user_request>` blocks marked as data.
- **Guardrails + PII redaction** — safety-guard sub-agent, pack-declared refusal topics, credit-card/SSN redaction callbacks.

Demo: `uv run python scripts/run_security_demo.py`.

---

## Project structure

```
OptiBuild/
├── app/                        # Concierge (ADK root agent)
│   ├── agent.py                #   root_agent + optimize_request tool (PII redaction)
│   ├── safety.py               #   imposed safety gate (fail-open, pack safety_notes)
│   ├── concierge.py            #   the ONE optimizer loop + modelize factories
│   ├── concierge_runner.py     #   wiring: extractor + judge + solver client
│   ├── modelization.py         #   4 staged LLM extractions (+ one-shot path)
│   ├── evaluator.py            #   deterministic completeness/coherence checks
│   ├── llm_extractor.py / llm_judge.py / prompt_contracts.py / extraction_schemas.py
│   ├── schema.py               #   Pivot Schema + A2A/MCP contracts (Pydantic)
│   ├── prompts/                #   concierge + safety-guard prompts (generic)
│   └── mcp_server/             # FastMCP server (7 tools, stdio)
│       ├── pack.py             #   active dataset-pack resolution (GAUSS_DATA_DIR)
│       ├── catalog.py          #   metadata, search, category resolution, loading
│       ├── cleaning.py         #   systematic cleaning (cost-column driven)
│       ├── safe_ops.py         #   expr allowlist, CleanOps, effect validation
│       ├── prefilter.py        #   single-category constraint prefilter
│       ├── cpsat.py            #   CP-SAT model builder + solver
│       └── ranking.py          #   K-candidate enumeration + TOPSIS
├── solver_app/                 # Solver Specialist (A2A-exposable)
│   ├── agent.py                #   solve() + agent card
│   ├── pipeline.py             #   deterministic pipeline (resolution → gates → clean → solve)
│   └── gates.py                #   Gate 1/2 (data coverage decisions)
├── data/pc-csv/                # default demo pack (25 PC-component CSVs + metadata.json)
├── scripts/                    # demos + gen_metadata.py
├── tests/                      # unit + integration (+ fixtures/toy-pack)
└── specs/                      # architecture, workflows, tasks
```

## Testing

```bash
uv run pytest                    # full suite (99 tests, offline)
uv run pytest tests/unit         # unit only
uv run ruff check .              # lint
```

### Evaluation suite (internal / admin only)

The 23-case `agents-cli` evaluation runs the **live agent** and spends real LLM
credits. It is gated behind an explicit opt-in and refuses to run without it:

```powershell
$env:GAUSS_EVAL_ENABLED = "1"                    # admin opt-in (required)
uv run python scripts/run_eval.py                # generate traces (fast mode, ~5x cheaper)
uv run python scripts/run_eval.py --mode staged  # full staged loop + LLM judge
uv run python scripts/run_eval.py --grade --project <GCP_PROJECT>  # + Vertex grading
```

Cost-control env vars:

| Variable | Effect |
|---|---|
| `GAUSS_EVAL_ENABLED=1` | Unlocks the eval tooling (`scripts/run_eval.py`, `tests/eval/simulate_dataset.py`) |
| `GAUSS_FAST_MODELIZATION=1` | One-shot modelization + deterministic evaluation — a single iteration of the same concierge loop (~5x fewer LLM calls); set automatically by `run_eval.py --mode fast` |

Results land in `artifacts/traces/` (generation) and `artifacts/eval/` (grading);
scores are recorded in `docs/eval-report.md`.

---

## Status & roadmap

**Done:** pivot schema & contracts, MCP server (7 tools), CP-SAT + TOPSIS solver, data gates, systematic/dynamic cleaning (security-hardened, wired by default), staged & one-shot modelization in a single unified concierge loop, hybrid evaluator with repair loop, imposed safety gate, ADK chat entry point, domain-agnostic dataset packs, category resolution.

**Open** (see [`specs/tasks.md`](specs/tasks.md)):
- A2A over HTTP (solver currently called in-process; contract identical)
- Budget sanitization at intake
- Phase 7: `agents-cli eval` suite (23 cases) + Cloud Run / Agent Engine deployment

## Team

Yanis · Kebei · Alex · Ayush · Palak
