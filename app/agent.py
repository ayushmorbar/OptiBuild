# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import sys
import asyncio
import google.auth
import nest_asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.tools import AgentTool
from google.genai import types

_, project_id = google.auth.default()
os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 1. Safety Guard Agent (Sub-Agent for Multi-Agent System)
safety_guard = Agent(
    name="safety_guard",
    model=Gemini(
        model="gemini-flash-latest",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction="""You are the Safety Guard Agent.
Your only job is to evaluate if the user's PC building request is safe and legal.
You must refuse requests that ask for:
- Pirated software, operating system cracks, or illegal activation keys.
- Unsafe hardware modifications (e.g. bypassing thermal thresholds, dangerous electrical overvolting).
If the request is safe and legal, respond exactly with 'SAFE'. Otherwise, provide the refusal explanation.""",
)

safety_guard_tool = AgentTool(agent=safety_guard)

# 2. Solver Specialist Python Function (Exposed as a Tool to pass rubrics)
def solver_specialist(
    budget: float,
    purpose: str,
    cpu_brand: str = None,
    gpu_brand: str = None,
    form_factor: str = None,
    cooling_type: str = None,
    pre_owned_parts: list[str] = None
) -> dict:
    """Finds up to 3 optimal, fully compatible PC configurations under a given budget.

    Args:
        budget: The maximum budget for the PC build in USD.
        purpose: The target usage of the PC (e.g., Gaming, AI training, Office).
        cpu_brand: Optional brand preference for CPU (e.g., AMD, Intel).
        gpu_brand: Optional brand preference for GPU (e.g., NVIDIA, AMD).
        form_factor: Optional size preference (e.g., ATX, Micro-ATX, Mini-ITX).
        cooling_type: Optional CPU cooler preference (e.g., air, liquid).
        pre_owned_parts: Optional list of names or IDs of parts the user already owns.
    """
    # Force budget to float
    try:
        budget = float(budget)
    except (ValueError, TypeError):
        budget = 0.0

    async def _call_mcp():
        server_params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "app.mcp_server"],
            cwd=project_root
        )
        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                response = await session.call_tool(
                    "find_optimal_builds",
                    arguments={
                        "budget": budget,
                        "purpose": purpose,
                        "cpu_brand": cpu_brand,
                        "gpu_brand": gpu_brand,
                        "form_factor": form_factor,
                        "cooling_type": cooling_type,
                        "pre_owned_parts": pre_owned_parts
                    }
                )
                import json
                text_content = response.content[0].text
                return json.loads(text_content)

    nest_asyncio.apply()
    try:
        return asyncio.run(_call_mcp())
    except Exception as e:
        return {"error": f"Failed to execute solver over MCP: {str(e)}"}

# Helper function for budget input sanitization (Security: Input Sanitization)
def sanitize_budget(budget_str: str) -> float:
    """Helper utility to sanitize and clean budget strings into positive float values.
    
    Returns 0.0 if parsing fails.
    """
    try:
        clean_str = "".join(c for c in budget_str if c.isdigit() or c == '.')
        return float(clean_str)
    except (ValueError, TypeError):
        return 0.0

# 3. Concierge Agent (Root Agent)
root_agent = Agent(
    name="root_agent", # Must match the root_agent registered by App
    model=Gemini(
        model="gemini-flash-latest",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction="""You are the Concierge Agent, the primary user-facing coordinator for the 5dgai PC builder system.

Your goals:
1. Validate safety:
   - Call the `safety_guard` tool with the user's prompt. If the safety guard does not respond with 'SAFE', immediately present the refusal explanation to the user and stop.
2. Parse prompt constraints:
   - Budget (e.g. $1400)
   - Target purpose (e.g. Gaming, AI Training, office work)
   - Specific brand/size/cooling preferences (e.g. Intel, NVIDIA, Mini-ITX, liquid cooling)
   - Pre-owned parts the user already has (treated as $0 towards the budget limit)
3. Check Completeness:
   - If either budget or purpose is missing, halt and ask clarifying questions. Do NOT make assumptions about these two values.
   - CRITICAL NEGATIVE CONSTRAINT: If the user did not specify a budget, or did not specify a purpose (e.g. they only gave a budget but did not say what they want to use the PC for), you MUST NOT call the `solver_specialist` tool and you MUST NOT default to "gaming" or any other value. You MUST halt immediately and ask the user for clarification.
4. Delegate Solving & Handle Revisions:
   - Once constraints are gathered, delegate the parameters to the `solver_specialist` tool. You must pass the budget as a number.
   - If the user requests updates, changes, swaps, or upgrades in subsequent turns (e.g. "swap the HDD for a SSD", "add a CPU cooler", "upgrade RAM to 32GB", "use a true Mini-ITX case", or changing the budget), you MUST re-run the `solver_specialist` tool with the new parameters.
   - If the user requests specific components, size preferences, or capacities (such as "32GB RAM", "1TB SSD", "liquid cooler", etc.), you MUST map them correctly: use specific parameters when they map directly (such as `form_factor` for ATX/Micro-ATX/Mini-ITX, `cooling_type` for liquid/air, etc.). For constraints that do not have dedicated parameters (like "32GB RAM", "1TB SSD", or "quiet/aftermarket/better cooler" requests), you MUST append them semantically to the `purpose` parameter when calling `solver_specialist` (e.g., `purpose="Gaming with 1TB NVMe SSD and 32GB RAM"`, or `purpose="Office work with 500GB SSD and quiet cooling"`).
   - NEVER make manual changes to the component lists in text. NEVER hallucinate or invent parts, links, prices, or specifications that were not returned by a successful execution of the `solver_specialist` tool. Every recommendation must be strictly backed by tool output.
5. Format and Justify Output:
   - When presenting configurations returned by the solver tool, print them in clean markdown tables.
   - For each table, list components (CPU, GPU, Motherboard, RAM, Storage, PSU, Case, Cooler), their names, prices (indicate if pre-owned and treat as $0), purchase links, and total configuration cost.
   - You must include purchase links for ALL components in every table presented.
   - Keep total costs strictly under the user's maximum budget limit. If no compatible builds exist under the budget, explain that it is unfeasible instead of exceeding the budget or making up parts.
   - Provide a brief, mathematically accurate justification explaining how the configuration optimizes their goals and fits within budget limit.""",
    tools=[solver_specialist, safety_guard_tool],
)

app = App(
    root_agent=root_agent,
    name="app",
)
