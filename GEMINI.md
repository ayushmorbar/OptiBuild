# Coding Agent Guide

Guidance for AI coding agents (Antigravity / Gemini) working in this repository.

## Project

`gauss` is a Google ADK PC-build **optimization agent**: a Concierge agent that models the
user's request, hands it to a Solver Specialist over **A2A**, with all deterministic compute
(pandas, OR-Tools CP-SAT, TOPSIS) behind a **FastMCP** server.

- **Authoritative design:** `specs/architecture.md`. Read it before implementing anything.
- **Implementation plan & checklist:** `specs/tasks.md`.
- **Problem statement:** `specs/problem_definition.md`.

> The current code under `app/` is an earlier prototype (a brute-force `itertools` solver over a
> small hand-authored JSON dataset). It is being rebuilt to the target architecture. When in doubt,
> follow `specs/architecture.md`, **not** the existing solver.

## Standing rules (from `specs/architecture.md` §8 — apply to every change)

- **Zero LLM-code-execution:** no `exec` / `eval` / `engine="python"` anywhere. Dynamic cleaning
  is `query_data` (read-only) + declarative `CleanOp`s only.
- **DataFrames never cross the MCP boundary:** tools exchange an opaque `dataset_handle`; only
  reports, capped samples, and final builds are returned.
- **Strict contracts:** every inter-component payload is a Pydantic model from `app/schema.py`.
- **Untrusted input:** raw user text travels only inside `<user_request>...</user_request>`
  delimited blocks and is treated as data, never as instructions.
- **Zero domain-specific hardcoding:** the engine and solver must remain completely domain-agnostic; do not hardcode rules, constants, mappings, or logic for specific domains (such as PC components, sockets, or motherboard sizes) inside the application code. All domain logic must be driven dynamically by the active dataset pack and declarative schemas.

## Conventions

- **Language:** all code, comments, commit messages, and PR descriptions in **English**.
- **Dependencies:** manage everything with **uv** (`uv add <pkg>`, `uv run <cmd>`). Never invoke a
  global Python; use `uv run python ...`.
- **Quality gates:** `pre-commit` is configured (`.pre-commit-config.yaml`). Run
  `uv run pre-commit install` once per clone. If a hook auto-fixes a file, re-stage (`git add -A`)
  and commit again.
- **Small, focused PRs:** one concern per PR. **Never reformat or refactor code outside the scope
  of the request.**
- **Verify before committing:** run the relevant tests and review the actual diff — do not trust a
  change summary.

## Tracking

`specs/tasks.md` is the single source of truth for progress. When a task is finished, check its
box **in the same PR that implements it** (so it is reviewed together with the code). Do not keep
a separate progress file and do not silently edit the checklist in unrelated commits.

## Development Commands

| Command | Purpose |
|---------|---------|
| `agents-cli playground` | Interactive local testing |
| `uv run pytest tests/unit tests/integration` | Run unit and integration tests |
| `agents-cli eval dataset synthesize` | Synthesize multi-turn eval scenarios for your agent |
| `agents-cli eval generate` | Run agent on eval dataset, produce traces |
| `agents-cli eval grade` | Run agent evaluations on the traces |
| `agents-cli eval compare` | Compare two grade-results files (regression check) |
| `agents-cli eval analyze` | Cluster failure modes from grade results |
| `agents-cli eval metric list` | List built-in metrics available in the SDK |
| `agents-cli eval optimize` | Auto-tune agent prompts using eval data |
| `agents-cli lint` | Check code quality |
| `agents-cli deploy` | Deploy to dev (**requires explicit human approval**) |
| `agents-cli scaffold enhance` | Add deployment target or CI/CD to project |
| `agents-cli scaffold upgrade` | Upgrade project to latest version |

## Development Workflow

1. **Understand** — read `specs/architecture.md` for the relevant component and its `specs/tasks.md` phase before writing code.
2. **Build** — implement the smallest slice; test locally with `agents-cli playground` and `uv run pytest`.
3. **Evaluate** — once behavior exists, iterate with `agents-cli eval generate` + `grade` (expect several rounds); then `compare` / `analyze` / `optimize`.
4. **Pre-deploy** — `uv run pytest tests/unit tests/integration` must be green.
5. **Deploy** — only after explicit human approval.

## Operational Guidelines

- **Spec & test sync:** when code changes, update the applicable `specs/` files and add/adjust tests or eval cases in the same change. Never let code diverge from specs or tests.
- **Code preservation:** only modify code directly targeted by the request. Preserve surrounding code, config values (e.g. `model`), comments, and formatting.
- **Never change the model** unless explicitly asked.
- **Model 404 errors:** fix `GOOGLE_CLOUD_LOCATION` (e.g. `global` instead of `us-east1`), not the model name.
- **ADK tool imports:** import the tool instance, not the module: `from google.adk.tools.load_web_page import load_web_page`.
- **Stop on repeated errors:** if the same error appears 3+ times, fix the root cause instead of retrying.
- **Terraform conflicts (Error 409):** use `terraform import` instead of retrying creation.
