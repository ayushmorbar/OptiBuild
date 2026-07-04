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


# ---------------------------------------------------------------------------
# A2A Contract types (§3)
# ---------------------------------------------------------------------------


class ObjectiveReportItem(BaseModel):
    """An item in the objective report detailing targets and values."""

    target: str = Field(..., description="Target variable name.")
    direction: Literal["maximize", "minimize"] = Field(
        ..., description="Direction of optimization."
    )
    value: float = Field(..., description="Resulting value for this objective.")


class Ranking(BaseModel):
    """Multi-objective ranking result metadata."""

    method: str = Field(..., description="Ranking method used, e.g. 'topsis'.")
    score: float = Field(..., description="Normalized TOPSIS score.")
    candidates_ranked: int = Field(
        ..., description="Total candidates evaluated in the ranking."
    )


class SolverResult(BaseModel):
    """Selections and metrics for a successful solver run."""

    selections: dict[str, dict] = Field(
        ..., description="Selected components, keyed by category."
    )
    derived_values: dict[str, float] = Field(
        default_factory=dict, description="Values of derived variables."
    )
    objective_report: list[ObjectiveReportItem] = Field(
        default_factory=list, description="Performance of objectives."
    )
    ranking: Ranking | None = Field(
        default=None,
        description="Ranking details if multi-objective optimization was used.",
    )


class MissingAttribute(BaseModel):
    """Details of a missing attribute required for optimization."""

    category: str = Field(..., description="The component category.")
    attribute: str = Field(..., description="The missing attribute column name.")
    referenced_by: list[str] = Field(
        default_factory=list, description="The constraints referencing this attribute."
    )


class RelaxationSuggestion(BaseModel):
    """A suggestion on how to relax a constraint to make the build feasible."""

    constraint: str = Field(..., description="Name of the constraint to relax.")
    suggestion: str = Field(..., description="Relaxation recommendation details.")


class SolverFeedback(BaseModel):
    """Feedback details populated when the solver is infeasible or has missing data."""

    reason: str = Field(
        ..., description="Human-readable reason for the solver failure."
    )
    missing_attributes: list[MissingAttribute] = Field(
        default_factory=list, description="List of attributes needed but not found."
    )
    failed_constraints: list[str] = Field(
        default_factory=list, description="Constraints that could not be satisfied."
    )
    relaxation_suggestions: list[RelaxationSuggestion] = Field(
        default_factory=list, description="Suggestions for making the request feasible."
    )


SolverStatus = Literal["SUCCESS", "INFEASIBLE", "MISSING_DATA", "ERROR"]


class SolverRequestContext(BaseModel):
    """Context metadata passed alongside the solver request."""

    original_prompt: str = Field(..., description="Verbatim raw user request prompt.")
    locale_currency: str = Field(
        default="USD", description="Currency code for price computations."
    )


class SolverRequest(BaseModel):
    """A request payload sent to the Solver Specialist."""

    transaction_id: str = Field(..., description="Unique transaction UUID.")
    iteration: int = Field(
        default=1, description="Iteration attempt number of the Concierge."
    )
    pivot_schema: PivotSchema = Field(
        ..., description="The Pivot Schema optimization model."
    )
    context: SolverRequestContext = Field(
        ..., description="Metadata and prompt context."
    )


class SolverResponse(BaseModel):
    """A response payload returned by the Solver Specialist."""

    transaction_id: str = Field(..., description="Unique transaction UUID.")
    status: SolverStatus = Field(..., description="Solver execution status.")
    result: SolverResult | None = Field(
        default=None, description="The build solution. Present only if SUCCESS."
    )
    feedback: SolverFeedback | None = Field(
        default=None, description="Details on failure. Present only if not SUCCESS."
    )
    trace: dict = Field(
        default_factory=dict, description="Diagnostics, timings, and metadata."
    )


# ---------------------------------------------------------------------------
# Evaluator Optimizer Loop types (§5)
# ---------------------------------------------------------------------------


class EvaluatorScores(BaseModel):
    """Scores assigned by the Evaluator judge across multiple dimensions."""

    completeness: float = Field(
        ..., description="Completeness score between 0.0 and 1.0."
    )
    coherence: float = Field(..., description="Coherence score between 0.0 and 1.0.")
    intent_fidelity: float = Field(
        ..., description="Fidelity score between 0.0 and 1.0."
    )


class FidelityViolation(BaseModel):
    """A missing or misaligned user requirement found by the Evaluator."""

    user_phrase: str = Field(
        ..., description="The user prompt phrase expressing intent."
    )
    problem: str = Field(
        ..., description="Why the pivot schema does not satisfy the phrase."
    )
    suggestion: str = Field(
        ..., description="Actionable suggestion to resolve the violation."
    )


class FeedbackDetails(BaseModel):
    """Structured details of evaluation failures for modelization optimizer loop."""

    target_stages: list[int] = Field(
        default_factory=list, description="Stages that need to be re-run, e.g. [1, 4]."
    )
    missing_categories: list[str] = Field(
        default_factory=list,
        description="List of required categories that are missing.",
    )
    coherence_violations: list[str] = Field(
        default_factory=list, description="Contradictions and invalid ranges found."
    )
    fidelity_violations: list[FidelityViolation] = Field(
        default_factory=list, description="Mismatches between user prompt and schema."
    )
    solver_feedback: SolverFeedback | None = Field(
        default=None,
        description="Solver failure details if loop trigger was solver error.",
    )


class EvaluationFeedback(BaseModel):
    """Feedback payload produced by the Evaluator optimizer loop."""

    passed: bool = Field(
        ..., description="Whether the pivot schema passed all thresholds."
    )
    iteration: int = Field(..., description="The loop iteration sequence number.")
    scores: EvaluatorScores = Field(
        ..., description="Scores for completeness/coherence/fidelity."
    )
    feedback_details: FeedbackDetails = Field(
        ..., description="Detailed feedback on violations."
    )
