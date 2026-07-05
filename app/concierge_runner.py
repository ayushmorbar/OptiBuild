"""Concierge Runner wiring the real LLM extractor, judge, and in-process solver client.

Fully pack-driven: the active dataset pack (GAUSS_DATA_DIR, default data/pc-csv)
supplies the catalog, the completeness policy, and the domain prompt context.
"""


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

    return run_concierge(
        user_request=user_request,
        catalog_summary=catalog.build_catalog_summary(metadata),
        extractor=make_llm_extractor(),
        judge=make_llm_judge(),
        solver_client=solver_client,
        required_categories=metadata.get("required_categories"),
        domain=catalog.get_domain_context(metadata),
    )
