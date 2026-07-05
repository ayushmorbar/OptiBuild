"""LLM-driven dynamic cleaning (workflow node n7/n8): the agent queries the
loaded dataframes' shape and submits declarative CleanOps through a tool —
no pack-specific code, no generated code.

The planner LLM sees only column names + a few sample values per category
(never full dataframes) and returns a CleanOp list; every op is then strictly
validated and executed by fixed server code (app/mcp_server/safe_ops.py).
Fail-open by design: any planner failure means "no dynamic cleaning".
"""

import json
import logging

from pydantic import BaseModel

from app.mcp_server import safe_ops
from app.mcp_server.store import store
from solver_app.dynamic_clean_prompt import build_dynamic_clean_prompt

logger = logging.getLogger(__name__)

DYNAMIC_CLEAN_THINKING_BUDGET = 512
_SAMPLE_TEXT_COLS = ("name", "color", "type")
_SAMPLE_VALUES = 5


class MapEntry(BaseModel):
    key: str
    value: str


class CleanOpLite(BaseModel):
    """Flat op model for Gemini structured output (no discriminated unions).

    Strict validation happens later in safe_ops.clean_dynamic.
    """

    op: str
    category: str
    column: str | None = None
    columns: list[str] | None = None
    value: str | None = None
    negate: bool = False
    expr: str | None = None
    mapping: list[MapEntry] | None = None
    min: float | None = None
    max: float | None = None


class CleanOpsPlan(BaseModel):
    """Container schema for CleanOps to avoid top-level list additionalProperties compatibility issues."""

    ops: list[CleanOpLite]


def _op_to_dict(op: CleanOpLite) -> dict:
    d = op.model_dump(exclude_none=True)
    if op.op != "filter_contains":
        d.pop("negate", None)
    if "mapping" in d and isinstance(d["mapping"], list):
        d["mapping"] = {item["key"]: item["value"] for item in d["mapping"]}
    return d


def make_dynamic_clean_hook(model: str = "gemini-flash-latest"):
    """Return a pipeline hook(handle, schema, original_prompt) planning CleanOps via LLM."""
    client = None

    def hook(handle: str, schema, original_prompt: str = "") -> None:
        nonlocal client
        user_request = original_prompt or getattr(schema, "user_intent", "")
        if not user_request:
            return

        try:
            frames = store.get(handle)
            categories = sorted(frames.keys())
            columns_by_category = {c: list(frames[c].columns) for c in categories}
            samples = {}
            for c in categories:
                parts = []
                for col in _SAMPLE_TEXT_COLS:
                    if col in frames[c].columns:
                        vals = (
                            frames[c][col]
                            .dropna()
                            .astype(str)
                            .unique()[:_SAMPLE_VALUES]
                        )
                        parts.append(f"{col}: {', '.join(vals)}")
                if parts:
                    samples[c] = " | ".join(parts)

            prompt = build_dynamic_clean_prompt(
                user_request, categories, columns_by_category, samples
            )

            from google import genai
            from google.genai import types

            if client is None:
                client = genai.Client()
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=CleanOpsPlan,
                    temperature=0.0,
                    thinking_config=types.ThinkingConfig(
                        thinking_budget=DYNAMIC_CLEAN_THINKING_BUDGET
                    ),
                ),
            )

            ops: list[CleanOpLite] = []
            if getattr(response, "parsed", None):
                ops = response.parsed.ops
            elif getattr(response, "text", None):
                data = json.loads(response.text)
                if isinstance(data, dict) and "ops" in data:
                    ops = [CleanOpLite.model_validate(d) for d in data["ops"]]
                elif isinstance(data, list):
                    ops = [CleanOpLite.model_validate(d) for d in data]
            if not ops:
                return

            report = safe_ops.clean_dynamic(
                handle,
                [_op_to_dict(o) for o in ops],
                rationale=f"dynamic cleaning for: {user_request[:200]}",
            )
            logger.info(
                "dynamic cleaning: %d op(s) accepted, %d rejected",
                report.accepted_ops,
                len(report.rejected),
            )
            for rej in report.rejected:
                logger.warning("dynamic op %d rejected: %s", rej.op_index, rej.reason)
        except Exception as e:
            # Enhancement, never a dependency: fail open.
            logger.warning("dynamic cleaning skipped: %s", e)

    return hook
