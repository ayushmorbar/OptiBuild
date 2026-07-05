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
import google.auth
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.tools import AgentTool
from google.genai import types

if os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").upper() == "TRUE":
    _, project_id = google.auth.default()
    os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
    os.environ["GOOGLE_CLOUD_LOCATION"] = "global"

import re


def redact_text(text: str) -> str:
    """Redacts credit card numbers (13-16 digits with spaces/dashes) and SSNs."""
    # Match standard credit cards: 13-16 digits with optional spaces or dashes
    cc_pattern = r"\b(?:\d[ -]*?){13,16}\b"
    # Match standard US Social Security Numbers (SSN)
    ssn_pattern = r"\b\d{3}-\d{2}-\d{4}\b"

    text = re.sub(cc_pattern, "[REDACTED CREDIT CARD]", text)
    text = re.sub(ssn_pattern, "[REDACTED PII]", text)
    return text


async def before_model_redact_pii(callback_context, llm_request) -> None:
    """Pre-model callback to redact PII/credit cards from the request payload/history."""
    if llm_request.contents:
        for content in llm_request.contents:
            if content.parts:
                for part in content.parts:
                    if part.text:
                        part.text = redact_text(part.text)

    if llm_request.config and llm_request.config.system_instruction:
        if isinstance(llm_request.config.system_instruction, str):
            llm_request.config.system_instruction = redact_text(
                llm_request.config.system_instruction
            )
        elif hasattr(llm_request.config.system_instruction, "parts"):
            for part in llm_request.config.system_instruction.parts:
                if part.text:
                    part.text = redact_text(part.text)


async def after_model_redact_pii(callback_context, llm_response) -> None:
    """Post-model callback to redact PII/credit cards from generated response text."""
    if llm_response.content and llm_response.content.parts:
        for part in llm_response.content.parts:
            if part.text:
                part.text = redact_text(part.text)


def load_prompt(filename: str) -> str:
    """Helper to dynamically load prompt content from the prompts directory."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts", filename)
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


# 1. Safety Guard Agent (Sub-Agent for Multi-Agent System)
safety_guard = Agent(
    name="safety_guard",
    model=Gemini(
        model="gemini-flash-latest",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=load_prompt("safety_guard.txt"),
    before_model_callback=before_model_redact_pii,
    after_model_callback=after_model_redact_pii,
)

safety_guard_tool = AgentTool(agent=safety_guard)


# 2. Optimize PC Build Python Function (Exposed as a Tool)
def optimize_pc_build(user_request: str) -> dict:
    """Finds optimal, fully compatible PC configurations under a given budget and constraints.

    Args:
        user_request: A consolidated natural-language request containing budget, purpose, and constraints.
    """
    import app.concierge_runner

    try:
        return app.concierge_runner.run(user_request)
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}


# Helper function for budget input sanitization (Security: Input Sanitization)
def sanitize_budget(budget_str: str) -> float:
    """Helper utility to sanitize and clean budget strings into positive float values.

    Returns 0.0 if parsing fails.
    """
    try:
        clean_str = "".join(c for c in budget_str if c.isdigit() or c == ".")
        return float(clean_str)
    except (ValueError, TypeError):
        return 0.0


# 3. Concierge Agent (Root Agent)
root_agent = Agent(
    name="root_agent",  # Must match the root_agent registered by App
    model=Gemini(
        model="gemini-flash-latest",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=load_prompt("concierge_agent.txt"),
    tools=[optimize_pc_build, safety_guard_tool],
    before_model_callback=before_model_redact_pii,
    after_model_callback=after_model_redact_pii,
)

app = App(
    root_agent=root_agent,
    name="app",
)
