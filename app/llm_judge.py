"""LLM intent-fidelity judge wiring for the Concierge evaluation."""

import json

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from app.llm_extractor import JUDGE_THINKING_BUDGET
from app.prompt_contracts import build_judge_prompt
from app.schema import FidelityViolation, PivotSchema


class JudgeResult(BaseModel):
    """Structured response for the intent-fidelity judge."""

    score: float = Field(..., ge=0.0, le=1.0)
    violations: list[FidelityViolation] = Field(default_factory=list)


def make_llm_judge(model="gemini-flash-latest"):
    """Create and return a lazy intent-fidelity judge callable."""
    client = None

    def judge(
        user_request: str, schema: PivotSchema
    ) -> tuple[float, list[FidelityViolation]]:
        nonlocal client
        if client is None:
            client = genai.Client()

        # Compact schema dump: defaults/nulls carry no signal for the judge
        schema_json = json.dumps(
            schema.model_dump(exclude_defaults=True, exclude_none=True),
            separators=(",", ":"),
        )
        # Ground the judge in the actual available columns (filtered to the
        # schema's categories) so it never demands data that does not exist.
        try:
            from app.mcp_server import catalog

            meta = catalog.load_metadata()
            cats = sorted({dv.category for dv in schema.decision_variables})
            available = catalog.build_catalog_summary(meta, categories=cats)
        except Exception:
            available = ""
        prompt = build_judge_prompt(user_request, schema_json, available)
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=JudgeResult,
                temperature=0.0,
                thinking_config=types.ThinkingConfig(
                    thinking_budget=JUDGE_THINKING_BUDGET
                ),
            ),
        )

        try:
            if hasattr(response, "parsed") and response.parsed is not None:
                res = response.parsed
                return res.score, res.violations

            data = json.loads(response.text)
            parsed = JudgeResult.model_validate(data)
            return parsed.score, parsed.violations
        except Exception:
            # Defensively fallback to 1.0 (pass) on parsing errors
            return 1.0, []

    return judge
