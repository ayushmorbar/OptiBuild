"""LLM extractor wiring for the Concierge staged modelization."""

import json

from google import genai
from google.genai import types

from app.extraction_schemas import (
    ConstraintLite,
    DecisionVariableLite,
    DerivedVariableLite,
    ObjectiveLite,
)

# Bounded thinking budgets per modelization stage (tokens). Unbounded dynamic
# thinking is the dominant hidden output cost; we keep reasoning where it drives
# modeling quality and cap it where the task is closer to translation.
THINKING_BUDGETS = {
    1: 512,  # decision variables: which categories fit the intent
    2: 512,  # derived variables: which aggregates matter for the goals
    3: 1024,  # objectives + weights: the core OR-modeling judgment
    4: 512,  # constraints: translating explicit bounds
}
ONESHOT_THINKING_BUDGET = 1024  # does all four stages in one pass
JUDGE_THINKING_BUDGET = 512


def make_llm_extractor(model="gemini-flash-latest"):
    """Create and return a lazy structured extraction callable.

    - GOOGLE_API_KEY is used automatically from the environment.
    """
    client = None

    stage_schemas = {
        1: list[DecisionVariableLite],
        2: list[DerivedVariableLite],
        3: list[ObjectiveLite],
        4: list[ConstraintLite],
    }

    def extractor(stage: int, prompt: str) -> list[dict]:
        nonlocal client
        if client is None:
            client = genai.Client()

        response_schema = stage_schemas[stage]
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=response_schema,
                temperature=0.0,
                thinking_config=types.ThinkingConfig(
                    thinking_budget=THINKING_BUDGETS[stage]
                ),
            ),
        )

        try:
            if hasattr(response, "parsed") and response.parsed is not None:
                items = response.parsed
                if isinstance(items, list):
                    return [
                        (
                            item.model_dump()
                            if hasattr(item, "model_dump")
                            else (item.__dict__ if hasattr(item, "__dict__") else item)
                        )
                        for item in items
                    ]

            data = json.loads(response.text)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "items" in data:
                return data["items"]
            return [data]
        except Exception:
            return []

    return extractor


def make_oneshot_extractor(model="gemini-flash-latest"):
    """Create and return a lazy one-shot extraction callable."""
    from app.extraction_schemas import PivotSchemaLite

    client = None

    def oneshot(prompt: str) -> dict:
        nonlocal client
        if client is None:
            client = genai.Client()

        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=PivotSchemaLite,
                temperature=0.0,
                thinking_config=types.ThinkingConfig(
                    thinking_budget=ONESHOT_THINKING_BUDGET
                ),
            ),
        )

        try:
            if hasattr(response, "parsed") and response.parsed is not None:
                parsed = response.parsed
                return (
                    parsed.model_dump()
                    if hasattr(parsed, "model_dump")
                    else (parsed.__dict__ if hasattr(parsed, "__dict__") else parsed)
                )

            return json.loads(response.text)
        except Exception:
            return {}

    return oneshot
