# GAUSS — System Workflow (Presentation Version)

Simplified view of `specs/workflow-final.md` for oral presentation: the agents and the
main steps, nothing else.

**One sentence:** GAUSS turns a free-form request into a formal optimization model,
solves it exactly, and returns the best possible selection — the LLM does the
*understanding*, deterministic code does the *math*.

```mermaid
flowchart TB
    USER(["👤 User<br>free-form request"])

    subgraph CONCIERGE["🤵 CONCIERGE AGENT (Gemini)"]
        direction TB
        S1["1 · Understand & secure<br><i>maturity check, gather goals & limits;<br>imposed safety gate before modelization</i>"]
        S2["2 · Model the problem<br><i>variables · objectives · constraints</i>"]
        S3["3 · Validate & self-correct<br><i>evaluator + LLM judge, up to 3 passes</i>"]
    end

    subgraph SOLVER["🔧 SOLVER SPECIALIST"]
        direction TB
        S4["4 · Prepare the data<br><i>match categories, clean,<br>filter on-the-fly (e.g. 'Intel only')</i>"]
        S5["5 · Solve & rank<br><i>CP-SAT exact optimization<br>+ TOPSIS for multiple objectives</i>"]
    end

    PACK[("📦 DATASET PACK<br>CSVs + metadata<br><i>all domain knowledge lives here</i>")]

    USER --> S1 --> S2 --> S3
    S3 -- "validated model" --> S4 --> S5
    S5 -- "6 · optimal selection" --> USER
    S3 -. "needs clarification" .-> USER
    S5 -. "infeasible → feedback" .-> S2
    PACK -.-> S2
    PACK -.-> S4

    style USER fill:#4a5568,color:#fff
    style S1 fill:#FFCDD2
    style S2 fill:#FFCDD2
    style S3 fill:#dd6b20,color:#fff
    style S4 fill:#fff3b0
    style S5 fill:#2b6cb0,color:#fff
    style PACK fill:#2f855a,color:#fff
```

## The agents

| Agent | Role | Nature |
|---|---|---|
| **Concierge** | Talks to the user, models the problem, validates it | LLM (Gemini, ADK) |
| **Safety Gate** | Screens every request before the loop (imposed workflow node, fail-open on technical failure) | Direct LLM check |
| **LLM Judge** | Checks the model matches the user's *intent* | LLM sub-step |
| **Solver Specialist** | Prepares data and computes the optimum | Deterministic pipeline + one LLM data-filtering step |

## The 6 steps

1. **Understand & secure** — gather goals, limits, preferences until the request is refined enough; the imposed safety gate then screens it before anything runs.
2. **Model** — the request becomes a formal OR model: decision variables, objectives, constraints.
3. **Validate & self-correct** — completeness/coherence checks + intent judge; the loop repairs itself (max 3 passes) before ever bothering the user.
4. **Prepare the data** — categories matched by metadata search; cleaning; qualitative needs ("an Intel CPU") become on-the-fly data filters.
5. **Solve & rank** — CP-SAT finds the exact optimum; TOPSIS ranks when objectives compete.
6. **Deliver** — the optimal selection, with totals and justification. Infeasible? The user gets actionable relaxation suggestions instead.

## Three ideas to remember

- **LLM never executes code** — it only *declares* (models, filters); validated server code executes.
- **Domain-agnostic** — swap the dataset pack, same engine optimizes PCs, meals, anything.
- **Exact math** — the final answer comes from a constraint solver, not from the LLM's imagination.
