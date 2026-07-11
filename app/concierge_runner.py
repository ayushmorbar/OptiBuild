"""Concierge Runner wiring the real LLM extractor, judge, and in-process solver client.

Fully pack-driven: the active dataset pack (GAUSS_DATA_DIR, default data/pc-csv)
supplies the catalog, the completeness policy, and the domain prompt context.

There is ONE concierge loop (app/concierge.py). GAUSS_FAST_MODELIZATION=1 only
parametrizes it: one-shot modelization, no LLM judge, max_iterations=1
(~5x fewer LLM calls; used for cost-bounded runs such as the eval suite).
"""

import os


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
    from app.concierge import (
        make_oneshot_modelizer,
        make_staged_modelizer,
        run_concierge,
    )
    from app.mcp_server import catalog
    from app.schema import SolverResponse

    metadata = catalog.load_metadata()
    catalog_summary = catalog.build_catalog_summary(metadata)
    domain = catalog.get_domain_context(metadata)

    def solver_client(req):
        resp_dict = solver_app.agent.solve(req.model_dump())
        return SolverResponse.model_validate(resp_dict)

    if os.environ.get("GAUSS_FAST_MODELIZATION") == "1":
        from app.llm_extractor import make_oneshot_extractor

        modelize = make_oneshot_modelizer(
            user_request, catalog_summary, make_oneshot_extractor(), domain=domain
        )
        judge = None
        max_iterations = 1
    else:
        from app.llm_extractor import make_llm_extractor
        from app.llm_judge import make_llm_judge

        modelize = make_staged_modelizer(
            user_request, catalog_summary, make_llm_extractor(), domain=domain
        )
        judge = make_llm_judge()
        max_iterations = 3

    return run_concierge(
        user_request=user_request,
        modelize=modelize,
        solver_client=solver_client,
        judge=judge,
        max_iterations=max_iterations,
        required_categories=metadata.get("required_categories"),
    )
