# Kaggle Capstone Project Spec: 5dgai Optimization Agent

This specification documents how the **5dgai - Optimisation Agent** implements and demonstrates the key concepts required for the **AI Agents: Intensive Vibe Coding Capstone Project** evaluation.

## Capstone Requirements & Demonstration Strategy

To satisfy the capstone project evaluation, we demonstrate at least **three (3) key concepts** across codebase implementation and video demonstration:

| Key Concept | Required Medium | Fulfilling Strategy in 5dgai Agent |
| :--- | :--- | :--- |
| **1. Agent / Multi-agent system (ADK)** | **Code** | **Multi-Agent Architecture**: We will split the system into a **Concierge Agent** (user-facing router/clarification assistant) and a **Solver Specialist Agent** (sub-agent focused strictly on solving component combinations) using the ADK A2A (Agent-to-Agent) protocol. |
| **2. MCP Server** | **Code** | **Decoupled Tool Hosting**: The components database and compatibility checkers are hosted in a separate process as a standard Model Context Protocol (MCP) Server. The `SolverSpecialistAgent` connects to it dynamically over Stdio using `McpToolset`. |
| **3. Security Features** | **Code or Video** | **Input Sanitization & Policy Guardrails**: We implement strict input validation to sanitize natural language inputs (e.g. non-negative budget casting) and safety prompt policies to prevent malicious recommendations (e.g., bypassing licenses or overclocking beyond safety limits). |
| **4. Agent skills (Agents CLI)** | **Code or Video** | **Evaluation & Quality Suite**: Full implementation of the `basic-dataset.json` containing 20 test cases and `eval_config.yaml` to run, grade, and optimize model performance using the `agents-cli eval` suite. |
| **5. Antigravity** | **Video** | Demonstrated by showcasing the development workflow, terminal logs, and agentic debugging sessions within the IDE in the capstone submission video. |
| **6. Deployability** | **Video** | Demonstrated by showing the live-running agent deployed to Google Cloud target environments (e.g. Cloud Run or Vertex AI Agent Runtime) using `agents-cli deploy`. |

---

## Technical Details of Fulfilling Concepts

### 1. Multi-Agent Design (ADK A2A)
The root agent (`ConciergeAgent`) will act as the user interaction coordinator. It will:
1. Parse user requests.
2. Interactively clarify missing constraints (budget, purpose).
3. Delegate the structured search parameters to `SolverSpecialistAgent` via A2A.

The `SolverSpecialistAgent` will wrap the tool loaded from the MCP server.

### 2. MCP Server Implementation
We separate the deterministic math/business logic from the LLM orchestrator:
* **`app/mcp_server.py`**: A standard Stdio MCP server built using FastMCP. It exposes `find_optimal_builds` as a tool.
* **`app/agent.py`**: The `SolverSpecialistAgent` loads toolsets dynamically via:
  ```python
  from google.adk.tools.mcp_tool import McpToolset
  from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams

  tools = McpToolset(
      connection_params=StdioConnectionParams(
          command="uv",
          args=["run", "python", "-m", "app.mcp_server"]
      )
  )
  ```

### 3. Security & Safety Implementation
We enforce safety at two levels:
* **System Prompt Guardrails**: The agent is instructed to refuse recommendations that facilitate cracking software, bypassing license verification, or suggesting hardware modifications that exceed manufacturer thermal/power limits.
* **Input Casting Sanitization**: The input parsing utility strictly sanitizes extracted budget parameters to verify they are non-negative numeric floats before forwarding to the solver engine.

### 4. Agent CLI & Eval Skills
Our evaluation suite measures agent quality across:
* **`multi_turn_task_success`**: Scoring if the agent correctly guides the user to a valid PC configuration under their specified budget.
* **`final_response_quality`**: Evaluating the correctness, completeness, and clarity of the formatted component tables and explanations.
* **`multi_turn_tool_use_quality`**: Ensuring the agent selects and invokes the solver tool with the correct arguments.
