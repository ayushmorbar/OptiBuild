"""app/schema.py — Pivot schema: the contract between Orchestrator, Evaluator and Solver."""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Leaf types
# ---------------------------------------------------------------------------

AttrType = Literal["float", "int", "str", "bool"]

# Restricted formula grammar for derived variables (NOT executable code):
#   expr   := agg "(" term ("," term)* ")" | term
#   agg    := "sum" | "min" | "max" | "avg" | "count"
#   term   := <category> "." <attribute> | <derived_name>
_TERM = r"[a-z0-9_-]+(?:\.[a-z0-9_]+)?"
_FORMULA_RE = re.compile(
    rf"^(?:(sum|min|max|avg|count)\(\s*{_TERM}(?:\s*,\s*{_TERM})*\s*\)|{_TERM})$"
)


class AttributeRequirement(BaseModel):
    """A dataset column the solver must have for one component category."""

    name: str = Field(
        ..., description="Column name in the category CSV, e.g. 'price', 'tdp'."
    )
    data_type: AttrType = Field(
        ..., description="Primitive type expected after cleaning."
    )
    unit: str | None = Field(
        default=None,
        description="Physical unit if any, e.g. 'W', 'USD', 'GB'. For display only.",
    )


class DecisionVariable(BaseModel):
    """One component category to pick exactly one part from."""

    category: str = Field(
        ...,
        pattern=r"^[a-z0-9-]+$",
        description="Dataset category key, e.g. 'cpu', 'video-card', 'power-supply'.",
    )
    required_attributes: list[AttributeRequirement] = Field(
        ...,
        min_length=1,
        description="Columns needed for this category. 'price' is always required implicitly.",
    )
    optional: bool = Field(
        default=False,
        description="True for nice-to-have categories (e.g. 'case-fan') the solver may drop "
        "if data is missing (Gate 2 logic, §6).",
    )


class DerivedVariable(BaseModel):
    """A computed aggregate over selected parts. Declared by the LLM, compiled by code."""

    name: str = Field(..., pattern=r"^[a-z0-9_]+$", description="e.g. 'total_price'.")
    formula: str = Field(
        ...,
        description="Expression in the restricted grammar, e.g. "
        "'sum(cpu.price, video-card.price, memory.price)'. Never free Python.",
    )
    dependencies: list[str] = Field(
        ...,
        description="Category keys and/or derived-variable names used in the formula.",
    )

    @field_validator("formula")
    @classmethod
    def formula_matches_grammar(cls, v: str) -> str:
        if not _FORMULA_RE.match(v.strip()):
            raise ValueError(f"formula {v!r} does not match the restricted grammar")
        return v.strip()


class Objective(BaseModel):
    """One optimization target. 1 objective → CP-SAT direct; ≥2 → TOPSIS (§7)."""

    target_variable: str = Field(
        ..., description="A derived-variable name or 'category.attribute' term."
    )
    direction: Literal["maximize", "minimize"] = Field(...)
    weight: float = Field(
        default=1.0,
        gt=0.0,
        description="Relative importance for TOPSIS. Normalized to sum=1 by the solver.",
    )
    rationale: str = Field(
        default="",
        description="One sentence tying this objective to the user's words (Evaluator "
        "intent-fidelity input).",
    )


# --- Threshold union: literal | KB reference | variable reference -----------


class LiteralThreshold(BaseModel):
    kind: Literal["literal"] = "literal"
    value: float | int | str | bool


class KBRefThreshold(BaseModel):
    """Symbolic threshold resolved by workflow node G against the knowledge base."""

    kind: Literal["kb_ref"] = "kb_ref"
    ref: str = Field(
        ...,
        pattern=r"^kb:[a-z0-9_]+/[a-z0-9-]+\.[a-z0-9_]+$",
        description="Format 'kb:<use_case>/<category>.<attribute>', e.g. "
        "'kb:gaming_cyberpunk_2077/video-card.memory'.",
    )


class VarRefThreshold(BaseModel):
    """Compares against another selected part's attribute; enforced inside CP-SAT."""

    kind: Literal["var_ref"] = "var_ref"
    ref: str = Field(
        ...,
        pattern=r"^[a-z0-9-]+\.[a-z0-9_]+$|^[a-z0-9_]+$",
        description="'category.attribute' term or a derived-variable name, "
        "e.g. 'power-supply.wattage'.",
    )


Threshold = Annotated[
    LiteralThreshold | KBRefThreshold | VarRefThreshold,
    Field(discriminator="kind"),
]


class Constraint(BaseModel):
    """Hard or soft bound. Single-component + literal → pandas pre-filter; else CP-SAT."""

    name: str = Field(
        ..., pattern=r"^[a-z0-9_]+$", description="Slug, e.g. 'budget_cap'."
    )
    left_side: str = Field(
        ..., description="'category.attribute' term or derived-variable name."
    )
    operator: Literal["<", "<=", "==", ">=", ">", "!="] = Field(...)
    right_side: Threshold = Field(...)
    is_hard: bool = Field(
        default=True,
        description="Hard → CP-SAT must satisfy; soft → penalty objective.",
    )
    origin: Literal[
        "user_explicit", "kb_derived", "compatibility", "system_default"
    ] = Field(
        default="user_explicit",
        description="Provenance, used by the relaxation strategy on INFEASIBLE (§11-Q2).",
    )

    @property
    def stage(self) -> Literal["prefilter", "solver"]:
        """Derived, never LLM-set. Single-component rules with a concrete (literal or
        KB-resolvable) bound run in the pandas pre-filter (workflow NOTE1); anything
        referencing derived variables or other parts runs in CP-SAT."""
        single_component = "." in self.left_side
        concrete = self.right_side.kind in ("literal", "kb_ref")
        return (
            "prefilter"
            if (single_component and concrete and self.is_hard)
            else "solver"
        )


# ---------------------------------------------------------------------------
# Root
# ---------------------------------------------------------------------------


class PivotSchema(BaseModel):
    """The single contract produced by the Orchestrator, scored by the Evaluator,
    and executed by the Solver Specialist."""

    schema_version: Literal["1.0"] = "1.0"
    user_intent: str = Field(
        ..., description="One-paragraph normalized restatement of the user's goal."
    )
    use_cases: list[str] = Field(
        default_factory=list,
        description="KB use-case slugs detected in the request, e.g. "
        "['gaming_cyberpunk_2077']. Empty if the request is fully explicit.",
    )
    decision_variables: list[DecisionVariable] = Field(..., min_length=1)
    derived_variables: list[DerivedVariable] = Field(default_factory=list)
    objectives: list[Objective] = Field(..., min_length=1)
    constraints: list[Constraint] = Field(default_factory=list)

    # ---- cross-reference integrity ----------------------------------------

    def _known_terms(self) -> set[str]:
        terms = {dv.name for dv in self.derived_variables}
        for d in self.decision_variables:
            for attr in d.required_attributes:
                terms.add(f"{d.category}.{attr.name}")
        return terms

    @model_validator(mode="after")
    def check_references(self) -> PivotSchema:
        known = self._known_terms()
        categories = {d.category for d in self.decision_variables}

        for dv in self.derived_variables:
            for dep in dv.dependencies:
                if dep not in categories and dep not in {
                    x.name for x in self.derived_variables
                }:
                    raise ValueError(
                        f"derived variable {dv.name!r}: unknown dependency {dep!r}"
                    )

        for obj in self.objectives:
            if obj.target_variable not in known:
                raise ValueError(
                    f"objective targets unknown variable {obj.target_variable!r}"
                )

        for c in self.constraints:
            if c.left_side not in known:
                raise ValueError(
                    f"constraint {c.name!r}: unknown left_side {c.left_side!r}"
                )
            if c.right_side.kind == "var_ref" and c.right_side.ref not in known:
                raise ValueError(
                    f"constraint {c.name!r}: unknown var_ref {c.right_side.ref!r}"
                )

        if len({c.name for c in self.constraints}) != len(self.constraints):
            raise ValueError("constraint names must be unique")
        return self

    @model_validator(mode="after")
    def normalize_weights(self) -> PivotSchema:
        total = sum(o.weight for o in self.objectives)
        for o in self.objectives:
            o.weight = o.weight / total
        return self
