# 5dgai Optimization Agent: Step-by-Step Development History

This document chronicles the design, implementation, evaluation, and optimization phases of the 5dgai PC Builder Optimization Agent.

---

## Phase 1: Planning and Specification Alignment
* **BDD Scenarios & Goal Analysis**: Analyzed the system requirements to formulate Behavior-Driven Development (BDD) scenarios covering:
  - Input parsing (budgets, purposes, and component preferences).
  - Safety constraints (illegal software, unsafe overclocking/overvolting checks).
  - Completeness validation (ensuring budget and purpose are specified before running calculations).
* **Architecture Mapping**: Selected a modular design utilizing:
  - **Concierge Agent**: User-facing coordinator for input parsing, safety, and formatting.
  - **Safety Guard Subagent**: An isolated agent delegated to run safety validation rules.
  - **Stdio MCP Server**: Local Model Context Protocol server executing deterministic compatibility checking and combinatorial knapsack optimization.

---

## Phase 2: Solver Implementation & Database Setup
* **Database Creation**: Created the local database file [components.json](file:///home/kejia/gauss/app/data/components.json) populated with detailed specifications, pricing, and purchase links.
* **Database Upgrades**: Added low-budget parts (e.g. Intel Core i3-12100, Gigabyte H610M motherboard, stock cooler, integrated graphics, Rosewill case) to prevent solver failure on tight budget constraints (e.g. $500 office PC).
* **Compatibility Logic**: Implemented deterministic checkers in [tools.py](file:///home/kejia/gauss/app/tools.py) verifying:
  - CPU-Motherboard socket compatibility.
  - Motherboard-RAM generation compatibility.
  - Motherboard-Case form factor sizing.
  - CPU-Cooler socket compatibility.
  - Power Supply Unit (PSU) capacity with a 20% safety margin.

---

## Phase 3: MCP Server Setup & Agent Wiring
* **MCP Server Implementation**: Created [mcp_server.py](file:///home/kejia/gauss/app/mcp_server.py) using the Python `mcp` SDK to register the `find_optimal_builds` solver as an MCP tool.
* **Agent Stdio Connection**: Wired the Concierge Agent in [agent.py](file:///home/kejia/gauss/app/agent.py) to launch the MCP server over stdio and make calls to the tool programmatically.
* **Multi-Agent Setup**: Configured the Concierge Agent to delegate safety checks to the `safety_guard` subagent.

---

## Phase 4: Setting Up Multi-Turn Evaluation
* **Trace Simulation Harness**: Developed [simulate_dataset.py](file:///home/kejia/gauss/tests/eval/simulate_dataset.py) to programmatically run our 20 evaluation prompts from [basic-dataset.json](file:///home/kejia/gauss/tests/eval/datasets/basic-dataset.json) through the agent via `InMemoryRunner`.
* **Gemini User Simulator**: Integrated a user simulator powered by `gemini-2.5-flash` to simulate natural consumer dialogue and follow-up adjustments (e.g., asking for cooler upgrades, swapping HDDs for SSDs, or requesting a smaller case).
* **Trace Schema Serialization**: Wrote custom serialization logic that cleans the trace events to include only `author` and `content` fields (filtering out internal Pydantic fields) so they successfully validate against the strict Vertex AI `EvaluationDataset` model.

---

## Phase 5: Optimization & Quality Iteration
Through multi-turn grading and `agents-cli eval analyze` diagnostics, we resolved several critical bugs:
1. **Pre-Owned Cost Bug**: Discovered that singular parts keys (like `"cpu"`, `"gpu"`) did not align with plural database categories (like `"cpus"`, `"gpus"`), causing pre-owned parts to not be calculated as $0. We mapped the keys correctly in the solver loop.
2. **Stock Cooler Filtering**: Configured the solver to filter out the Stock CPU cooler if keywords like `"quiet"`, `"silent"`, or `"aftermarket"` are found in the target `purpose` string.
3. **Form Factor Case Restrictions**: Restricted case filtering to true Mini-ITX Small Form Factor cases when `form_factor` is set to "Mini-ITX".
4. **Prompt Enforcement**: Hardened the Concierge Agent's instructions to prevent it from defaulting to "gaming" or assuming budgets, forcing it to halt and ask clarifying questions instead. We also instructed it to delegate all adjustments back to the solver tool to prevent manual text editing and price hallucinations.
5. **PII and Credit Card Redaction**: Integrated `before_model_callback` and `after_model_callback` hooks in [app/agent.py](file:///home/kejia/gauss/app/agent.py) to automatically redact credit card numbers and Social Security Numbers from user prompts, history, system instructions, and generated responses before model API calls are made or displayed.

### Development Progress Metrics
These fixes dramatically boosted evaluation results:

| Metric | Baseline | Optimized | Improvement |
| :--- | :--- | :--- | :--- |
| **`multi_turn_task_success_v1` (Mean Score)** | `0.5877` | **`0.8924`** | **+30.47%** |
| **`multi_turn_task_success_v1` (Pass Rate)** | `20.00%` | **`73.68%`** | **+53.68%** |
| **`multi_turn_tool_use_quality_v1` (Mean Score)** | `0.8389` | **`0.9491`** | **+11.02%** |
| **`multi_turn_tool_use_quality_v1` (Pass Rate)** | `40.00%` | **`60.00%`** | **+20.00%** |
