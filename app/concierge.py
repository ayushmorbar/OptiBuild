"""Concierge Optimizer Loop combining staged modelization, evaluation, and solving."""

import uuid

from app.evaluator import evaluate_deterministic
from app.modelization import run_modelization
from app.schema import SolverRequest, SolverRequestContext


def run_concierge(
    user_request: str,
    catalog_summary: str,
    extractor,
    judge,
    solver_client,
    max_iterations: int = 3,
) -> dict:
    """Tie modelization, evaluator, and the A2A solver client into a 3-iteration loop."""
    prior_schema = None
    target_stages = None
    repair_feedback = None

    feedback = None
    response = None
    for iteration in range(1, max_iterations + 1):
        try:
            schema = run_modelization(
                user_request,
                catalog_summary,
                extractor,
                prior_schema=prior_schema,
                target_stages=target_stages,
                repair_feedback=repair_feedback,
            )
        except Exception as e:
            target_stages = [1, 2, 3, 4]
            repair_feedback = str(e)
            continue

        # 1. Gate check on deterministic dimensions first
        det = evaluate_deterministic(schema, iteration)

        # 2. Run LLM judge only if deterministic constraints pass
        if det.scores.completeness >= 0.80 and det.scores.coherence >= 0.80:
            fidelity, fviol = judge(user_request, schema)
            feedback = evaluate_deterministic(
                schema,
                iteration,
                intent_fidelity=fidelity,
                fidelity_violations=fviol,
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

    if not questions:
        if repair_feedback:
            questions.append(repair_feedback)
        else:
            questions.append(
                "Could not satisfy the request with a valid, feasible PC build."
            )

    return {
        "status": "NEEDS_CLARIFICATION",
        "schema": prior_schema,
        "questions": questions,
        "iterations": max_iterations,
    }
