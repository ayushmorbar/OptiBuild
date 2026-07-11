"""Concierge Optimizer Loop combining modelization, evaluation, and solving.

There is ONE loop. Execution modes only differ by its parameters:
- default: staged modelization (make_staged_modelizer), LLM judge, 3 iterations
- fast/eval: one-shot modelization (make_oneshot_modelizer), judge=None, 1 iteration
"""

import uuid

from app.evaluator import evaluate_deterministic
from app.modelization import build_schema_oneshot, run_modelization
from app.schema import SolverRequest, SolverRequestContext


def make_staged_modelizer(user_request, catalog_summary, extractor, domain=None):
    """Adapter: staged 4-stage modelization with targeted REPAIR support."""

    def modelize(prior_schema=None, target_stages=None, repair_feedback=None):
        return run_modelization(
            user_request,
            catalog_summary,
            extractor,
            prior_schema=prior_schema,
            target_stages=target_stages,
            repair_feedback=repair_feedback,
            domain=domain,
        )

    return modelize


def make_oneshot_modelizer(user_request, catalog_summary, oneshot_extractor, domain=None):
    """Adapter: one-shot modelization. Repair inputs are ignored — every call
    is a fresh full extraction (fast config runs with max_iterations=1)."""

    def modelize(prior_schema=None, target_stages=None, repair_feedback=None):
        return build_schema_oneshot(
            user_request, catalog_summary, oneshot_extractor, domain=domain
        )

    return modelize


def run_concierge(
    user_request: str,
    modelize,
    solver_client,
    judge=None,
    max_iterations: int = 3,
    required_categories: list[str] | None = None,
) -> dict:
    """Run the concierge loop: modelization, evaluation, and solving.

    - `modelize(prior_schema, target_stages, repair_feedback) -> PivotSchema`:
      built with make_staged_modelizer or make_oneshot_modelizer.
    - `judge(user_request, schema) -> (fidelity, violations)`, or None to skip
      the intent-fidelity check (deterministic evaluation only).
    - `required_categories` is the active pack's completeness policy
      (metadata.json `required_categories`, optional).

    Returns a dict with `status` ("SUCCESS" | "NEEDS_CLARIFICATION"), `schema`,
    `iterations`, plus `solver_response` when the solver ran and `questions`
    on clarification.
    """
    prior_schema = None
    target_stages = None
    repair_feedback = None

    feedback = None
    response = None
    for iteration in range(1, max_iterations + 1):
        try:
            schema = modelize(
                prior_schema=prior_schema,
                target_stages=target_stages,
                repair_feedback=repair_feedback,
            )
        except Exception as e:
            target_stages = [1, 2, 3, 4]
            repair_feedback = str(e)
            continue

        # 1. Gate check on deterministic dimensions first
        det = evaluate_deterministic(
            schema, iteration, required_categories=required_categories
        )

        # 2. Run the LLM judge only if present and deterministic constraints pass
        if (
            judge is not None
            and det.scores.completeness >= 0.80
            and det.scores.coherence >= 0.80
        ):
            fidelity, fviol = judge(user_request, schema)
            feedback = evaluate_deterministic(
                schema,
                iteration,
                intent_fidelity=fidelity,
                fidelity_violations=fviol,
                required_categories=required_categories,
            )
        else:
            feedback = det

        # 3. Check if evaluation passed
        if not feedback.passed:
            prior_schema = schema
            target_stages = feedback.feedback_details.target_stages or [
                1,
                2,
                3,
                4,
            ]

            reasons = []
            if feedback.feedback_details.missing_categories:
                # The agent must self-complete the configuration — name exactly
                # what stage 1 must add, never bounce this to the user.
                reasons.append(
                    "The schema is missing REQUIRED categories that must be added "
                    "as decision variables (do not ask the user, just include "
                    "them): " + ", ".join(feedback.feedback_details.missing_categories)
                )
            if feedback.feedback_details.coherence_violations:
                reasons.extend(feedback.feedback_details.coherence_violations)
            if feedback.feedback_details.fidelity_violations:
                reasons.extend(
                    [v.problem for v in feedback.feedback_details.fidelity_violations]
                )
            if not reasons:
                reasons.append("Completeness or coherence checks failed.")

            repair_feedback = "; ".join(reasons)
            continue

        # 4. Evaluation passed: call the solver client
        request = SolverRequest(
            transaction_id=uuid.uuid4().hex,
            iteration=iteration,
            pivot_schema=schema,
            context=SolverRequestContext(original_prompt=user_request),
        )
        response = solver_client(request)

        if response.status == "SUCCESS":
            return {
                "status": "SUCCESS",
                "solver_response": response,
                "schema": schema,
                "iterations": iteration,
            }

        # 5. Solver failed (INFEASIBLE / MISSING_DATA / ERROR): loop again with feedback
        prior_schema = schema
        target_stages = [3, 4]
        repair_feedback = (
            response.feedback.reason
            if (response.feedback and response.feedback.reason)
            else "solver could not satisfy the request"
        )

    # Budget exhausted: return NEEDS_CLARIFICATION with final questions
    questions = []
    if response is not None and response.feedback and response.feedback.reason:
        questions.append(response.feedback.reason)
    elif feedback is not None:
        if feedback.feedback_details.coherence_violations:
            questions.extend(feedback.feedback_details.coherence_violations)
        if feedback.feedback_details.fidelity_violations:
            questions.extend(
                [v.problem for v in feedback.feedback_details.fidelity_violations]
            )
        if feedback.feedback_details.missing_categories:
            questions.append(
                "Missing required categories: "
                + ", ".join(feedback.feedback_details.missing_categories)
            )

    if not questions:
        if repair_feedback:
            questions.append(repair_feedback)
        else:
            questions.append(
                "Could not satisfy the request with a valid, feasible configuration."
            )

    result = {
        "status": "NEEDS_CLARIFICATION",
        "schema": prior_schema,
        "questions": questions,
        "iterations": max_iterations,
    }
    if response is not None:
        result["solver_response"] = response
    return result
