"""Concierge Runner wiring the real LLM extractor, judge, and in-process solver client.

Fully pack-driven: the active dataset pack (GAUSS_DATA_DIR, default data/pc-csv)
supplies the catalog, the completeness policy, and the domain prompt context.

Two execution modes:
- default: staged modelization (4 extractions + LLM judge, up to 3 repair iterations)
- GAUSS_FAST_MODELIZATION=1: one-shot extraction + deterministic evaluation only
  (~5x fewer LLM calls; used for cost-bounded runs such as the eval suite)
"""

import os
import uuid


def build_catalog_summary() -> str:
    """Catalog summary of the active pack (kept for backward compatibility)."""
    from app.mcp_server import catalog

    try:
        metadata = catalog.load_metadata()
    except OSError:
        return ""
    return catalog.build_catalog_summary(metadata)


def run(user_request: str) -> dict:
    """Execute the Concierge loop for a user request in-process."""
    import solver_app.agent
    from app.concierge import run_concierge
    from app.llm_extractor import make_llm_extractor
    from app.llm_judge import make_llm_judge
    from app.mcp_server import catalog
    from app.schema import SolverResponse

    metadata = catalog.load_metadata()

    def solver_client(req):
        resp_dict = solver_app.agent.solve(req.model_dump())
        return SolverResponse.model_validate(resp_dict)

    if os.environ.get("GAUSS_FAST_MODELIZATION") == "1":
        return _run_fast(user_request, metadata, solver_client)

    return run_concierge(
        user_request=user_request,
        catalog_summary=catalog.build_catalog_summary(metadata),
        extractor=make_llm_extractor(),
        judge=make_llm_judge(),
        solver_client=solver_client,
        required_categories=metadata.get("required_categories"),
        domain=catalog.get_domain_context(metadata),
    )


def _run_fast(user_request: str, metadata: dict, solver_client) -> dict:
    """Cost-bounded path: one-shot extraction + deterministic evaluation (no LLM judge).

    Single LLM call per request instead of 5+ per iteration. Returns the same
    result contract as run_concierge.
    """
    from app.evaluator import evaluate_deterministic
    from app.llm_extractor import make_oneshot_extractor
    from app.mcp_server import catalog
    from app.modelization import build_schema_oneshot
    from app.schema import SolverRequest, SolverRequestContext

    try:
        schema = build_schema_oneshot(
            user_request,
            catalog.build_catalog_summary(metadata),
            make_oneshot_extractor(),
            domain=catalog.get_domain_context(metadata),
        )
    except ValueError as e:
        return {
            "status": "NEEDS_CLARIFICATION",
            "schema": None,
            "questions": [str(e)],
            "iterations": 1,
        }

    feedback = evaluate_deterministic(
        schema, iteration=1, required_categories=metadata.get("required_categories")
    )
    if not feedback.passed:
        questions = list(feedback.feedback_details.coherence_violations)
        if feedback.feedback_details.missing_categories:
            questions.append(
                "Missing required categories: "
                + ", ".join(feedback.feedback_details.missing_categories)
            )
        return {
            "status": "NEEDS_CLARIFICATION",
            "schema": schema,
            "questions": questions or ["The extracted model failed validation."],
            "iterations": 1,
        }

    response = solver_client(
        SolverRequest(
            transaction_id=uuid.uuid4().hex,
            iteration=1,
            pivot_schema=schema,
            context=SolverRequestContext(original_prompt=user_request),
        )
    )
    if response.status == "SUCCESS":
        return {
            "status": "SUCCESS",
            "solver_response": response,
            "schema": schema,
            "iterations": 1,
        }
    return {
        "status": "NEEDS_CLARIFICATION",
        "schema": schema,
        "questions": [response.feedback.reason]
        if (response.feedback and response.feedback.reason)
        else ["Solver could not satisfy the request."],
        "solver_response": response,
        "iterations": 1,
    }
