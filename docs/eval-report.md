# GAUSS — Evaluation Report (agents-cli eval)

Capstone concept 4. Dataset: `tests/eval/datasets/basic-dataset.json` — **23 cases**
across five scenario classes (standard/happy ×5, budget-edge/infeasible ×3,
brand & constraint preferences ×9, ambiguous/missing-info ×3, guardrail & PII ×3).
Metrics (`tests/eval/eval_config.yaml`): `multi_turn_task_success`,
`final_response_quality`, `multi_turn_tool_use_quality` — graded by the Vertex AI
eval service via `agents-cli eval grade`.

## Method

1. **Generate** — agent traces produced by running the live root_agent
   (`optimize_request` + `safety_guard`, Gemini flash) over all 23 prompts:
   the CLI's staged inference runner, invoked directly to lift the CLI's global
   600 s timeout (23 concierge-loop cases ≫ 10 min).
2. **Grade** — `agents-cli eval grade --traces <traces>.json --config tests/eval/eval_config.yaml`.
3. **Triage** — `agents-cli eval analyze` on the results; prompt/normalization fixes;
   re-run; record baseline → final.

## Results

### Baseline (traces_baseline.json — <DATE>)

| Metric | Score |
|---|---|
| multi_turn_task_success | _pending_ |
| final_response_quality | _pending_ |
| multi_turn_tool_use_quality | _pending_ |

### Final (after iteration)

| Metric | Baseline | Final |
|---|---|---|
| multi_turn_task_success | _pending_ | _pending_ |
| final_response_quality | _pending_ | _pending_ |
| multi_turn_tool_use_quality | _pending_ | _pending_ |

## Failure analysis & fixes applied

_pending — populated from `agents-cli eval analyze` output._

Robustness fixes already applied during trace generation (LLM-output normalization in
`app/modelization.py`, observed live in the generate logs):
- `origin` synonyms (`user_request`, …) → valid literals
- Threshold `kind` synonyms (`variable`, `ref`, …) → `var_ref`/`literal`, plus
  content-based repair when `kind` contradicts the populated fields
- Dotted `dependencies` → category keys; snake_case targets → dotted terms
- Dangling-reference repair (`_assemble_schema`) with per-drop logged reasons

## Reproduce (admin only)

The eval is **gated**: it spends real LLM credits and refuses to run without the
explicit opt-in `GAUSS_EVAL_ENABLED=1`. Preferred entry point:

```powershell
$env:GAUSS_EVAL_ENABLED = "1"
uv run python scripts/run_eval.py --grade --project <PROJECT_ID>   # fast mode (default)
uv run python scripts/run_eval.py --mode staged                    # full-fidelity variant
```

Manual equivalent:

```bash
# 1. Generate (local agent; GOOGLE_CLOUD_PROJECT required)
agents-cli eval generate --dataset tests/eval/datasets/basic-dataset.json --output artifacts/traces/
# (or the staged runner directly, to avoid the CLI's 600s cap — see scripts/run_eval.py)

# 2. Grade (Vertex eval service; ADC + project required)
agents-cli eval grade --traces artifacts/traces/<file>.json \
  --config tests/eval/eval_config.yaml \
  --project <PROJECT_ID> --output artifacts/eval/<run>/

# 3. Analyze
agents-cli eval analyze artifacts/eval/<run>/<results>.json
```
