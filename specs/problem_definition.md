# Problem Definition: 5dgai - Optimisation Agent

## 1. Overview
The **5dgai - Optimisation Agent** is an agentic assistant designed to help users assemble multi-component products (e.g., PCs, drones, custom setups) online. 
Building these products requires:
- Understanding each component, their individual specifications, and mutual compatibility constraints.
- Optimizing for specific goals, such as achieving the lowest price for the highest efficiency or meeting a specific performance threshold under a budget limit.

Since LLMs are prone to hallucinating when dealing with large amounts of data in combinatorial constraint-satisfaction problems, this agent uses a deterministic harness (solver/checkers) to yield mathematically accurate and compatible configurations.

## 2. Target Audience & Users
- Enthusiasts, builders, or general consumers looking to assemble custom multi-component systems (initially focused on PC building).

## 3. Input Specification
The agent accepts fuzzy human inputs, which typically specify:
- **Purpose**: e.g., gaming (specific titles like Cyberpunk 2077, Rust), AI training, video editing, office work.
- **Budget**: Max budget constraint (e.g., $1400).
- **Preferences (Optional)**: Specific brands, form factors, or target specs (e.g., "Must have an NVIDIA GPU").

## 4. Output Specification
An optimal configuration list containing:
- Component names, categories, individual prices, purchase links, and mutual compatibility verification.
- Total cost of the configuration.
- Short reasoning justifying why this configuration best fits the user's purpose and constraints.

## 5. System Constraints & Safety Rules
- **No Hallucinated Parts**: Only recommend real, verified components from a database or search index.
- **Strict Budget Compliance**: The total configuration price must not exceed the user's specified maximum budget.
- **Strict Compatibility**: Every component in the configuration must be verified as compatible (e.g., CPU socket matching Motherboard socket, Motherboard fitting in the Case, Power Supply providing enough wattage, etc.).
- **Deterministic Harness**: All compatibility and budget computations must be handled or verified by deterministic code, not just prompt instructions.

## 6. Success Criteria
- The system correctly parses the user's budget and performance objectives.
- The returned configuration is 100% compatible.
- The total price of the configuration is within the budget constraint.
- The system returns up to 3 alternative optimal configurations when appropriate.
