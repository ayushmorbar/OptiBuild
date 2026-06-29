# Technical Design: 5dgai - Optimisation Agent

## 1. System Architecture
The system follows a modular, multi-agent ADK design utilizing a custom **MCP (Model Context Protocol) Server** for deterministic calculations:

```
                     +--------------------+
                     |    User Request    |
                     +---------+----------+
                               |
                               v
                     +---------+----------+
                     |   Concierge Agent  |
                     |    (ADK Agent)     |
                     +---------+----------+
                               |
                               | (A2A Delegation)
                               v
                     +---------+----------+
                     |  Solver Specialist |
                     |   (Sub-Agent)      |
                     +---------+----------+
                               |
                               | (McpToolset Stdio Client)
                               v
                     +---------+----------+
                     |     MCP Server     |
                     |  (app/mcp_server.py) |
                     +---------+----------+
                               |
                               v
                     +---------+----------+
                     |  Component Solver  |
                     |  & JSON Database   |
                     +--------------------+
```

## 2. Workflow Graph
The agent controls the interaction loop and hands off the combinatorial optimization task to the deterministic solver:

```mermaid
graph TD
    START([User Prompt]) --> ParseInput[Parse requirements: budget, purpose, preferences]
    ParseInput --> CheckCompleteness{Has Budget & Purpose?}
    CheckCompleteness -- No --> Clarify[Ask user for clarification]
    Clarify --> WaitUser([Wait for user response])
    WaitUser --> ParseInput
    CheckCompleteness -- Yes --> Solve[Run Deterministic Solver / Optimization]
    Solve --> VerifyCompatibility{Check compatibility & budget}
    VerifyCompatibility -- Valid Candidates Found --> FormulateConfig[Format configs: name, price, link, total]
    VerifyCompatibility -- No Candidates Found --> RaiseLimit[Inform user & suggest budget/spec adjustment]
    FormulateConfig --> Present[Present final configurations]
    RaiseLimit --> Present
    Present --> END([Done])
```

## 3. Components Database Schema (Local Prototype)
We will maintain a JSON-based database (`app/data/components.json`) containing component details.

The modular database schema defining all component types and required specification fields is documented in YAML format at:
* **[specs/components_schema.yaml](file:///home/kejia/gauss/specs/components_schema.yaml)**

## 4. Compatibility Rules (Deterministic Checkers)
Compatibility verification rules to be implemented in Python:
- **CPU & Motherboard**: `cpu.specs.socket == motherboard.specs.socket`
- **Power Supply (PSU) Capacity**: `psu.specs.wattage >= total_power_draw_w * 1.2` (including 20% safety margin).
  - `total_power_draw_w` = sum of `power_draw_w` of CPU, GPU, and estimated power draw for other components (e.g. 50W).
- **Case & Motherboard Form Factor**: Case must support motherboard form factor (e.g. an ATX case supports ATX/Micro-ATX motherboards).

## 5. ADK Agent & Tools Definition
The agent will be structured using Vertex AI ADK.

### Concierge Agent (`app/agent.py`)
- **System Prompt**: Acts as the user-facing assistant. It parses requirements, enforces security rules (refusing unsafe/illegal queries), interactively requests missing requirements, and delegates solving to the `SolverSpecialistAgent` via A2A protocol.

### Solver Specialist Agent
- **System Prompt**: Acts as the backend specialist for running calculations. It connects to the local MCP server over stdio and registers the MCP tools.
- **Tools**: Loads tool definitions dynamically from the local MCP server process (`app/mcp_server.py`) using `McpToolset`.

### MCP Server (`app/mcp_server.py`)
- Built using the Python `mcp` SDK (FastMCP).
- **Tools**:
  - `find_optimal_builds`: Exposes the deterministic optimization solver tool over Stdio transport.
- **Data**: Interacts directly with the components database JSON.
