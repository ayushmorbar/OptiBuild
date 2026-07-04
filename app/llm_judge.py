"""LLM intent-fidelity judge wiring for the Concierge evaluation."""

import json

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

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

        prompt = build_judge_prompt(user_request, schema.model_dump_json())
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=JudgeResult,
                temperature=0.0,
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
