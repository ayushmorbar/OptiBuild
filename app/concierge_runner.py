"""Concierge Runner wiring the real LLM extractor, judge, and in-process solver client."""

import json
from pathlib import Path


def build_catalog_summary() -> str:
    """Read data/pc-csv/metadata.json and construct a catalog summary string."""
    repo_root = Path(__file__).resolve().parents[1]
    metadata_path = repo_root / "data" / "pc-csv" / "metadata.json"
    if not metadata_path.exists():
        return ""
    with open(metadata_path, encoding="utf-8") as f:
        data = json.load(f)

    lines = []
    for ds in data.get("datasets", []):
        cat = ds.get("category_key")
        cols = list(ds.get("columns", {}).keys())
        lines.append(f"- Category: {cat}, Columns: {', '.join(cols)}")
    return "\n".join(lines)


def run(user_request: str) -> dict:
    """Execute the Concierge loop for a user request in-process."""
    import solver_app.agent
    from app.concierge import run_concierge
    from app.llm_extractor import make_llm_extractor
    from app.llm_judge import make_llm_judge
    from app.schema import SolverResponse

    def solver_client(req):
        resp_dict = solver_app.agent.solve(req.model_dump())
        return SolverResponse.model_validate(resp_dict)

    return run_concierge(
        user_request=user_request,
        catalog_summary=build_catalog_summary(),
        extractor=make_llm_extractor(),
        judge=make_llm_judge(),
        solver_client=solver_client,
    )
