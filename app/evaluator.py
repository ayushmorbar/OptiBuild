"""Deterministic Evaluator logic for PivotSchema coherence and completeness."""

from collections import defaultdict

from app.schema import (
    EvaluationFeedback,
    EvaluatorScores,
    FeedbackDetails,
    FidelityViolation,
    PivotSchema,
)


def check_coherence(schema: PivotSchema) -> tuple[float, list[str]]:
    """Verify that there are no contradictory constraints or objectives in the schema.

    Returns (coherence_score, list of violations).
    """
    violations = []

    # 1. Contradictory HARD literal bounds on the same left_side
    literal_bounds = defaultdict(list)
    for c in schema.constraints:
        if c.is_hard and c.right_side.kind == "literal":
            val = c.right_side.value
            if isinstance(val, (int, float)):
                literal_bounds[c.left_side].append((c.operator, float(val)))

    for left_side, bounds in literal_bounds.items():
        lower = None
        upper = None
        eq_vals = set()

        for op, val in bounds:
            if op == "==":
                eq_vals.add(val)
                if lower is None or val > lower:
                    lower = val
                if upper is None or val < upper:
                    upper = val
            elif op in (">", ">="):
                if lower is None or val > lower:
                    lower = val
            elif op in ("<", "<="):
                if upper is None or val < upper:
                    upper = val

        if len(eq_vals) > 1:
            violations.append(
                f"Contradictory equality bounds on '{left_side}': {sorted(eq_vals)}"
            )
        elif lower is not None and upper is not None and lower > upper:
            violations.append(
                f"Contradictory bounds on '{left_side}': "
                f"lower bound ({lower}) > upper bound ({upper})"
            )

    # 2. Objective target directions
    obj_dirs = defaultdict(set)
    for obj in schema.objectives:
        obj_dirs[obj.target_variable].add(obj.direction)
        if obj.weight is not None and obj.weight <= 0:
            violations.append(
                f"Objective '{obj.target_variable}' has non-positive weight {obj.weight}"
            )

    for target, dirs in obj_dirs.items():
        if "maximize" in dirs and "minimize" in dirs:
            violations.append(
                f"Contradictory directions on objective '{target}': "
                "both maximize and minimize requested"
            )

    score = 1.0 if not violations else 0.0
    return score, violations


def check_completeness(
    schema: PivotSchema, required_categories: list[str] | None = None
) -> tuple[float, list[str], list[str]]:
    """Verify that all target variables and refs resolve to known terms, and that
    the pack's required categories (if declared) are present in the decision variables.

    `required_categories` comes from the active dataset pack's metadata.json
    (`required_categories` top-level field). When the pack declares none,
    completeness is the resolvability fraction alone and no category is
    ever reported missing.

    With a required list, the score is the minimum of:
    1. The fraction of required categories present in the schema.
    2. The fraction of targets/refs in objectives/constraints that resolve to known terms.

    Returns (completeness_score, list of unresolved terms, list of missing categories).
    """
    known = set()
    for dv in schema.derived_variables:
        known.add(dv.name)
    for d in schema.decision_variables:
        for attr in d.required_attributes:
            known.add(f"{d.category}.{attr.name}")

    unresolved = []
    total = 0

    for obj in schema.objectives:
        total += 1
        if obj.target_variable not in known:
            unresolved.append(obj.target_variable)

    for c in schema.constraints:
        total += 1
        if c.left_side not in known:
            unresolved.append(c.left_side)
        if c.right_side.kind == "var_ref":
            total += 1
            if c.right_side.ref not in known:
                unresolved.append(c.right_side.ref)

    if total == 0:
        fraction_resolvable = 1.0
    else:
        resolvable_count = total - len(unresolved)
        fraction_resolvable = float(resolvable_count) / total

    if not required_categories:
        return fraction_resolvable, sorted(unresolved), []

    required = set(required_categories)
    present_categories = {d.category for d in schema.decision_variables}
    missing_categories = sorted(required - present_categories)

    fraction_required = (len(required) - len(missing_categories)) / len(required)

    combined_score = min(fraction_resolvable, fraction_required)
    return combined_score, sorted(unresolved), missing_categories


def evaluate_deterministic(
    schema: PivotSchema,
    iteration: int,
    intent_fidelity: float = 1.0,
    fidelity_violations: list[FidelityViolation] | None = None,
    required_categories: list[str] | None = None,
) -> EvaluationFeedback:
    """Run deterministic evaluator checks and output an EvaluationFeedback."""
    completeness, _, missing_categories = check_completeness(
        schema, required_categories
    )
    coherence, coh = check_coherence(schema)

    passed = completeness >= 0.80 and coherence >= 0.80 and intent_fidelity >= 0.80

    target_stages = []
    if completeness < 0.80:
        target_stages.append(1)
    if coherence < 0.80:
        target_stages.extend([3, 4])
    if intent_fidelity < 0.80:
        target_stages.extend([3, 4])

    return EvaluationFeedback(
        passed=passed,
        iteration=iteration,
        scores=EvaluatorScores(
            completeness=completeness,
            coherence=coherence,
            intent_fidelity=intent_fidelity,
        ),
        feedback_details=FeedbackDetails(
            target_stages=sorted(set(target_stages)),
            missing_categories=missing_categories,
            coherence_violations=coh,
            fidelity_violations=fidelity_violations or [],
            solver_feedback=None,
        ),
    )
