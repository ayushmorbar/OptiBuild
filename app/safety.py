"""Deterministic safety gate run before the Concierge loop.

Direct structured LLM check (NOT an ADK agent), imposed by concierge_runner
for every entry point (ADK chat, scripts, eval). Fail-open: any technical
failure (missing API key, network, quota, parse error) logs a warning and
lets the request proceed; refusal happens only on an explicit unsafe verdict.
"""

import logging
import os
import re

from google import genai
from google.genai import types
from pydantic import BaseModel

logger = logging.getLogger(__name__)

_GENERIC_REFUSAL = "This request cannot be processed."


def load_prompt(filename: str) -> str:
    """Load prompt content from the app/prompts directory."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts", filename)
    with open(path, encoding="utf-8") as f:
        return f.read().strip()


def redact_text(text: str) -> str:
    """Redacts credit card numbers (13-16 digits with spaces/dashes) and SSNs."""
    # Match standard credit cards: 13-16 digits with optional spaces or dashes
    cc_pattern = r"\b(?:\d[ -]*?){13,16}\b"
    # Match standard US Social Security Numbers (SSN)
    ssn_pattern = r"\b\d{3}-\d{2}-\d{4}\b"

    text = re.sub(cc_pattern, "[REDACTED CREDIT CARD]", text)
    text = re.sub(ssn_pattern, "[REDACTED PII]", text)
    return text


class SafetyVerdict(BaseModel):
    """Structured verdict of the safety gate."""

    safe: bool
    reason: str | None = None


def build_safety_instruction() -> str:
    """Generic safety prompt, extended with the active pack's domain safety notes."""
    instruction = load_prompt("safety_guard.txt")
    try:
        from app.mcp_server import catalog

        domain = catalog.get_domain_context(catalog.load_metadata())
        if domain.safety_notes:
            notes = "\n".join(f"- {note}" for note in domain.safety_notes)
            instruction += f"\nAdditionally refuse requests involving:\n{notes}\n"
    except Exception:
        # Missing/invalid pack must never break the gate; generic prompt suffices.
        pass
    return instruction


def make_safety_checker(model="gemini-flash-latest"):
    """Create a lazy safety-gate callable: user_request -> (safe, reason)."""
    client = None

    def check(user_request: str) -> tuple[bool, str | None]:
        nonlocal client
        try:
            if client is None:
                client = genai.Client()
            prompt = (
                build_safety_instruction()
                + "\n\n<user_request>\n"
                + redact_text(user_request)
                + "\n</user_request>"
            )
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=SafetyVerdict,
                    temperature=0.0,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
            if getattr(response, "parsed", None) is not None:
                verdict = response.parsed
            else:
                verdict = SafetyVerdict.model_validate_json(response.text)
        except Exception as e:
            logger.warning("Safety gate unavailable (%s); proceeding fail-open.", e)
            return True, None
        # Refusal decision stays outside the try: an explicit unsafe verdict
        # always refuses; only technical failures fail open.
        if verdict.safe:
            return True, None
        return False, verdict.reason or _GENERIC_REFUSAL

    return check
