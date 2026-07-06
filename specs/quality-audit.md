# GAUSS — Agent Quality Audit (Complete System)

**Date:** 2026-07-05 · **Auditor:** development-session review (code inspection + live probes)
**Scope:** the full agent system as built — ADK entry point, modelization loop, evaluator,
solver pipeline, MCP layer, dataset packs, deployment — against the design in
`specs/workflow.md` / `specs/architecture.md`.
**Method:** static audit of every LLM touchpoint, 108-test suite, measured token profiles,
and **live end-to-end probes** on the deployed Cloud Run service (multi-turn conversations,
adversarial user scenarios, dynamic-filtering proof).

## Executive summary

| Dimension | Grade | One-liner |
|---|---|---|
| Architecture conformance | **A** | Every workflow node now has a wired, tested owner — including n7 (dynamic cleaning), the last gap |
| LLM-output robustness | **A−** | 7 normalization/repair layers, all born from observed live failures, all regression-tested |
| Security | **A** | Zero code execution; closed vocabularies; literal-only matching; gated eval; private service |
| Correctness & tests | **B+** | 108 offline tests + live validations; no LLM-in-the-loop CI (by cost design) |
| Cost discipline | **B+** | Thinking bounded, retries capped, payloads lean; root-agent history still unbounded |
| Domain-agnosticism | **A−** | Toy-pack proof; one arithmetic enrichment remains as pack tooling (documented) |
| Ops & deployment | **B+** | Cloud Run live (8 revisions iterated), scale-to-zero, IAM-private; A2A HTTP pending |
| Evaluation (concept 4) | **C (pending)** | Assets & gated tooling ready; graded scores not yet recorded (admin run pending) |

**Overall: production-quality demo system.** The architecture's core promise — free-form
intent → validated OR model → exact solver, with no LLM-generated code executed anywhere —
is implemented, measured, and demonstrated live.

---

## 1. Architecture conformance (workflow → as-built)

Every node of the original modelization (`specs/workflow.md`) traced to running code:

| Workflow node | Implementation | Verified by |
|---|---|---|
| A→B chat entry | `app/agent.py` root_agent + `optimize_request` | deployed multi-turn runs |
| C1–E staged modelization | `app/modelization.py` (+ one-shot path) | unit tests, live traces |
| F pivot schema | `app/schema.py` (validators, grammar) | 20+ schema tests |
| EVAL completeness/coherence | `app/evaluator.py` (pack-driven required set) | truth-table tests |
| EVAL intent fidelity | `app/llm_judge.py` — **catalog-grounded** (cannot demand nonexistent data) | prompt tests + live |
| FB→REPAIR loop | `run_concierge` — feedback **names missing categories** | `test_repair_feedback_names_missing_categories` |
| n2 fetch + n9/n10 gates | `catalog.load_data` + `solver_app/gates.py` | gate truth tables |
| n5 systematic cleaning | `cleaning.py` (cost-column driven) | fixture tests |
| **n7/n8 dynamic cleaning** | **WIRED 2026-07-05**: `solver_app/dynamic_cleaner.py` — LLM sees columns + 5 sample values, emits closed-vocabulary CleanOps executed by fixed server code | live AMD-filter proof (below) |
| H prefilter | `prefilter.py` | unit + live (1413→958 brand filter during testing) |
| I/K/M CP-SAT + TOPSIS | `cpsat.py`, `ranking.py` | solver tests, deployed builds |
| n13→FB INFEASIBLE/MISSING | pipeline feedback + relaxation suggestions | integration tests |

**Key live proof of n7 (on-the-fly querying):** request *"cheapest PC with an AMD CPU"* —
the globally cheapest CPU is an Intel at $25; the planner emitted one
`filter_contains(cpu, name, "AMD")` op (accepted, 0 rejected) and the solver returned an
AMD at $46.79. The qualitative constraint was formulated **at runtime by the agent through
a tool**, with no pack-specific column or code.

## 2. LLM-output robustness (the reliability layer)

Every layer below was added in response to an **observed live failure**, and each is locked
by a regression test:

| # | Observed failure | Repair layer (`app/modelization.py` unless noted) |
|---|---|---|
| 1 | `data_type: "string"`, `direction: "min"` | synonym maps (types, directions) |
| 2 | `origin: "user_request"` → constraint dropped | origin synonym map + safe default |
| 3 | `kind: "variable"` / `"LiteralThreshold"` class-name echo | kind map + content-based literal/var_ref repair |
| 4 | formula `a.x + b.y` (off-grammar) | rewrite to `sum(a.x, b.y)` |
| 5 | `dependencies: ["cpu.price"]` (dotted terms) | stripped to category keys |
| 6 | target `memory_capacity` (snake_case) | resolved to dotted term + attribute auto-declared |
| 7 | dangling refs after item drops → crash | `_assemble_schema`: auto-declare / drop / clear error into REPAIR |

Additional agent-behavior hardening (all live-incident driven):
- **Tool-call contract** pinned in the concierge prompt after a `MALFORMED_FUNCTION_CALL`
  (hallucinated `category_resolution` argument).
- **Retry cap**: at most one `optimize_request` per user message (a silent 5-retry loop was
  observed costing ~75 LLM calls).
- **Self-completion**: missing required categories are fed back BY NAME to stage 1 and
  injected up-front via `DomainContext.required_categories` — the agent never asks the user
  to enumerate components (defect observed, fixed, tested).
- All validation drops are **logged with reasons** (no more silent degradation).

## 3. Security posture

- **Zero LLM code execution** — invariant re-verified this session: no `exec`/`eval`/
  `engine="python"` anywhere; grep-clean.
- **Closed CleanOp vocabulary** (now 5 ops): strict Pydantic (`extra="forbid"`), per-op
  rejection with reason, effect validation (columns/dtypes/rows), >90%-drop batch revert.
  New `filter_contains` matches **literal substrings only** (`regex=False` — `.*` matches
  nothing, tested).
- **Expression gate**: pandas-query strings token-allowlisted, numexpr-only.
- **Prompt-injection stance**: user text always inside `<user_request>` data blocks;
  red-team scenarios in `scripts/run_security_demo.py` + eval cases 21–23 (piracy, unsafe
  hardware, PII) with credit-card/SSN redaction callbacks.
- **Operational**: Cloud Run service is IAM-private (`--no-allow-unauthenticated`); the
  eval suite (real-credit spender) is admin-gated behind `GAUSS_EVAL_ENABLED=1` with safe
  defaults in `.env.example`.

## 4. Correctness & test coverage

- **108 offline tests** (unit + integration), ruff clean. Coverage spans schema validators,
  gates, safe-ops security cases, CP-SAT (incl. no-cost-column caps), TOPSIS determinism,
  evaluator, concierge loop, repair layers, dynamic-clean ops, eval gate, toy pack E2E.
- **Live validations performed**: local Docker end-to-end; deployed multi-turn conversation
  (clarification → confirmation → $262.08 build under a $1500 cap); dynamic AMD-filter
  proof (twice: with and without a brand column).
- **Gap (accepted)**: no LLM-in-the-loop CI — deliberate (cost); compensated by the
  normalization layers being pure functions with recorded real-world inputs as fixtures.

## 5. Cost discipline (measured)

| Item | Value |
|---|---|
| Happy-path request | ~8.1K tokens in / ≤4.4K out (thinking hard-capped at 3,072/iteration) |
| Stage prompts | 1,330 / 405 / 543 / 971 tok; judge schema 353 tok (compact dumps) |
| Tool return in history | ~590 tok (internal schema/trace stripped, JSON-safe) |
| Worst case | 3 repair iterations, 1 tool call/message → ~3–5¢; old ×5-retry pattern impossible |
| Dynamic cleaning | +1 bounded call (thinking 512), fail-open, `GAUSS_DYNAMIC_CLEAN=0` kill-switch |
| At rest | ~0€ (scale-to-zero) |

**Known cost gap:** root-agent conversation history grows unboundedly across turns (ADK
default). Long demos are fine; a pruning/summarization callback is the next lever.

## 6. Domain-agnosticism

- Engine holds **zero domain knowledge**; packs declare `domain`, `required_categories`,
  `primary_cost_column`, `safety_notes` (all optional → generic behavior).
- **Proof**: `tests/fixtures/toy-pack` (meal-plan, cost column `cost`) runs the identical
  pipeline E2E, including synonym category-resolution (`"main-dish"` → `protein`).
- Qualitative/textual requirements are handled **generically at runtime** (dynamic
  filtering) — the cpu `brand` enrichment was reverted on principle.
- **Documented exception**: `scripts/enrich_pc_pack.py` still derives memory
  `capacity_gb` (arithmetic over packed strings — not expressible as a runtime query).
  Classified as pack data curation, not engine knowledge.

## 7. Known gaps & risks (ranked)

| Sev | Gap | State / mitigation |
|---|---|---|
| M | **Eval scores not yet recorded** (capstone concept 4 artifact) | Assets + gated `scripts/run_eval.py` ready; fast mode ≈ €0.5–0.75/run |
| M | Root-agent history growth (cost + dilution on long chats) | Documented; pruning callback proposed |
| M | A2A HTTP endpoint pending (`a2a_app=None` fallback) | Contract identical in-process; export exists |
| L | Model alias `gemini-flash-latest` (behavior/pricing may drift) | Pin an explicit model version before the video |
| L | CP-SAT aggregates: only `sum` compiled (min/max/avg/count skipped) | Grammar accepts them; documented deferral |
| L | Socket compatibility (cpu↔motherboard) out of scope | No socket column in data; documented in spec |
| L | `list-apps` shows `data`/`solver_app` as selectable "apps" | Cosmetic (ADK dir scan); service is private |
| L | Budget sanitization at intake unwired | `sanitize_budget` exists; tracked in tasks.md 5.4 |

## 8. Recommendations (priority order)

1. **Run the gated eval** (fast mode) and record baseline scores in `docs/eval-report.md` —
   closes concept 4 and the last Phase-7 checkbox.
2. **Pin the model version** (replace the `-latest` alias) before recording the video.
3. Add a **history-pruning callback** on root_agent (drop tool-response bodies older than
   N turns) — biggest remaining cost/dilution lever.
4. Ship the A2A HTTP endpoint when the `a2a` dependency question is settled (post-capstone).

---

*Verification commands:* `uv run pytest` (108), `uv run ruff check .`,
`uv run python scripts/run_offline_demo.py`, `scripts/run_security_demo.py`,
`GAUSS_DATA_DIR=tests/fixtures/toy-pack uv run pytest tests/integration/test_toy_pack_pipeline.py`.
