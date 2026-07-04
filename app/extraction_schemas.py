"""Lite validation schemas for structured LLM extraction.

Gemini's response_schema does not support exclusiveMinimum/maximum, regex patterns,
discriminator unions, or multi-type fields. We define lite models here and validate
their output into strict app.schema models inside the pipeline.
"""

from pydantic import BaseModel


class AttrReqLite(BaseModel):
    name: str
    data_type: str
    unit: str | None = None


class DecisionVariableLite(BaseModel):
    category: str
    required_attributes: list[AttrReqLite]
    optional: bool = False


class DerivedVariableLite(BaseModel):
    name: str
    formula: str
    dependencies: list[str]


class ObjectiveLite(BaseModel):
    target_variable: str
    direction: str
    weight: float = 1.0
    rationale: str = ""


class ThresholdLite(BaseModel):
    kind: str
    value: float | None = None
    ref: str | None = None


class ConstraintLite(BaseModel):
    name: str
    left_side: str
    operator: str
    right_side: ThresholdLite
    is_hard: bool = True
    origin: str = "user_explicit"
    coefficient: float = 1.0
