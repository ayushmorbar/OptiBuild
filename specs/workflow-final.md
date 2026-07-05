# 5dgai — Optimisation Agent: Final System Workflow

As-built successor of `specs/workflow.md` (the initial modelization). It reflects the real,
verified structure of the system after the root_agent rewiring (commit `28d5ba8`).

Differences vs. the initial workflow:

- **Node G (KB → numeric thresholds) dropped** — owner decision 2026-07-04: qualitative intent
  becomes optimization *objectives*, explicit numbers become literal constraints. No knowledge base.
- **Note n8 superseded** — the LLM never generates/executes code: dynamic cleaning is read-only
  `query_data` + declarative `CleanOp`s validated server-side (zero `exec`/`eval`).
- **Evaluator is hybrid** — deterministic completeness (8 required categories) + coherence first;
  the LLM judge (intent fidelity) only runs when they pass.
- **Entry point is real** — `adk web` → `root_agent` → `optimize_request` tool → the full loop.
- **Domain-agnostic engine (2026-07-05)** — zero domain knowledge in code: the active *dataset
  pack* (`GAUSS_DATA_DIR`, default `data/pc-csv`) supplies the catalog, domain name, safety
  notes, `required_categories` (evaluator completeness) and `primary_cost_column` (implicit
  column, CP-SAT row-cap sort, cleaning rules). Decision-variable categories are resolved to
  catalog keys by metadata search (exact → synonym → fuzzy) before data loading.
- Yellow nodes mark the two remaining gaps: the dynamic-cleaning hook is implemented but not
  invoked by the pipeline, and the Solver is called in-process (A2A HTTP export pending).

```mermaid
---
config:
  layout: elk
---
flowchart TB
    START(("START")) --> A["Input: free-form request (chat / adk web)"]

    subgraph ROOT["Concierge root_agent — ADK LlmAgent (app/agent.py)"]
        B["root_agent (Gemini)<br>PII-redaction callbacks (before/after model)"]
        SG["safety_guard sub-agent<br>(AgentTool, refusal guardrails)"]
        OPB[["optimize_request tool<br>ONE consolidated NL request"]]
    end

    A --> B
    B -- "1 - safety check" --> SG
    SG -- "SAFE / refusal" --> B
    B -- "2 - consolidated request" --> OPB

    subgraph LOOP["Concierge Optimizer Loop — app/concierge.py (max 3 iterations)"]
        subgraph MODEL["OR Problem Modelization — 4 staged LLM extractions (app/modelization.py)"]
            C1["1a - DECISION VARIABLES<br>categories + required attributes"] --> C2["1b - DERIVED VARIABLES<br>restricted formula grammar (no code)"]
            C2 --> D["2 - OBJECTIVES<br>direction + weights + rationale"] --> E["3 - CONSTRAINTS<br>literal / var_ref thresholds (no KB)"]
        end
        F["Pivot schema (Pydantic)<br>app/schema.py — cross-ref validators"]
        EVAL{"EVALUATOR (deterministic)<br>completeness: 8 required categories<br>coherence: contradiction scan"}
        JUDGE["LLM judge (temp 0)<br>intent fidelity"]
        FB["Structured feedback<br>missing_categories / violations<br>target_stages for REPAIR"]
        GUARD{"iteration &lt; 3 ?"}
        ASK["NEEDS_CLARIFICATION<br>targeted questions"]
    end

    OPB --> C1
    E --> F --> EVAL
    EVAL -- "det pass (≥ 0.80)" --> JUDGE
    EVAL -- "below 0.80" --> FB
    JUDGE -- "below 0.80" --> FB
    FB --> GUARD
    GUARD -- "yes — re-run only target_stages" --> C1
    GUARD -- no --> ASK --> B

    JUDGE -- "pass" --> REQ[/"SolverRequest (pivot schema)<br>in-process call — A2A HTTP pending"/]

    subgraph SOLVER["Solver Specialist — solver_app/ (deterministic pipeline)"]
        SA["solve(): validates SolverRequest<br>runs run_solver_pipeline"]
        RES["Category resolution<br>search metadata: exact → synonym → fuzzy"]
        N2["load_data: match categories/columns<br>→ coverage report"]
        G1{"Gate 1: all decision vars<br>satisfied by data?"}
        G2{"Gate 2: missing var defines<br>a constraint / goal?"}
        N5["Systematic cleaning (pandas)<br>prices, coercion, IQR, memory quirks"]
        N7["Dynamic cleaning<br>query_data + declarative CleanOps<br>⚠️ implemented, hook NOT wired"]
        H["PRE-FILTER (pandas)<br>single-component literal rules"]
        I["CP-SAT: assemble valid builds<br>ExactlyOne / budget / var_ref headroom"]
        J{"# objectives ?"}
        K["CP-SAT optimizes directly"]
        M["TOPSIS (pymcdm)<br>rank K=50 candidates"]
        N13{"Found a config ?"}
    end

    REQ --> SA --> RES --> N2 --> G1
    G1 -- YES --> N5
    G1 -- NO --> G2
    G2 -- "NO — strip descriptive attrs" --> N5
    G2 -- "YES → MISSING_DATA" --> FB
    N5 -.->|"hook=None today"| N7
    N5 --> H
    H -- "required category emptied → INFEASIBLE" --> FB
    H --> I --> J
    J -- "1" --> K --> N13
    J -- "≥2" --> M --> N13
    N13 -- "YES → SUCCESS" --> OUT["SolverResponse → root_agent<br>markdown component table + total"]
    N13 -- "NO → INFEASIBLE<br>+ relaxation suggestions" --> FB
    OUT --> B
    B --> FIN(("END"))

    subgraph MCP["FastMCP Server — app/mcp_server (7 tools over Stdio; pipeline calls the same functions in-process)"]
        T1[["search_datasets"]]
        T2[["load_data"]]
        T3[["clean_systematic"]]
        T4[["query_data (read-only, numexpr)"]]
        T5[["clean_dynamic (CleanOps)"]]
        T6[["prefilter"]]
        T7[["solve_build (CP-SAT + TOPSIS)"]]
    end

    subgraph DATA["Data layer — dataset pack (GAUSS_DATA_DIR, default data/pc-csv)"]
        CSV[("pack CSVs (demo: 25 PC categories)")]
        META[("metadata.json catalog<br>domain, required_categories,<br>primary_cost_column, safety_notes,<br>columns, synonyms, quirks")]
    end

    RES -.-> T1
    N2 -.-> T2
    N5 -.-> T3
    N7 -.-> T4 & T5
    H -.-> T6
    I -.-> T7
    K -.-> T7
    M -.-> T7
    T1 -.-> META
    T2 -.-> CSV & META

    NOTE1["NOTE: KB node G dropped —<br>qualitative intent → objectives,<br>explicit numbers → literal constraints"]
    NOTE2["NOTE: zero LLM code execution —<br>allowlisted numexpr expressions,<br>closed CleanOp vocabulary"]
    E -.- NOTE1
    T5 -.- NOTE2

    style C1 fill:#FFCDD2
    style C2 fill:#FFCDD2
    style D fill:#FFCDD2
    style E fill:#FFCDD2
    style A stroke:#757575,fill:#757575,color:#ffffff
    style F fill:#4a5568,color:#fff
    style EVAL fill:#dd6b20,color:#fff
    style JUDGE fill:#dd6b20,color:#fff
    style FB fill:#fbd38d,color:#5c2e00
    style REQ fill:#d9edf7,stroke:#31708f
    style I fill:#2b6cb0,color:#fff
    style M fill:#2f855a,color:#fff
    style N7 fill:#fff3b0,stroke:#d4a017,stroke-width:2px
    style NOTE1 fill:#fff3b0,stroke:#d4a017,color:#5c4400
    style NOTE2 fill:#fff3b0,stroke:#d4a017,color:#5c4400
    style START fill:#2f855a,stroke:#00C853,color:#ffffff
    style FIN stroke:#D50000,fill:#D50000,color:#ffffff
```

## Legend / status

| Marker | Meaning |
|---|---|
| Red stages (C1–E) | LLM structured-output extractions (staged, REPAIR-able individually) |
| Orange (EVAL/JUDGE) | Hybrid evaluator — deterministic gates first, LLM judge gated behind them |
| Blue (CP-SAT) / Green (TOPSIS) | Deterministic optimization core (`app/mcp_server/cpsat.py`, `ranking.py`) |
| ⚠️ Yellow `N7` | Implemented & security-tested (`safe_ops.py`) but `dynamic_clean_hook=None` in the pipeline |
| `REQ` in-process note | Contract (`SolverRequest`/`SolverResponse`) is final; HTTP A2A export still pending (`a2a_app=None`) |
