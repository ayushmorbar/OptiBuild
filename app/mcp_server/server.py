"""MCP Server definition using FastMCP."""

import math

import pandas as pd
from mcp.server.fastmcp import FastMCP

from app.mcp_server import catalog, cleaning, cpsat, safe_ops
from app.mcp_server import prefilter as prefilter_mod

mcp = FastMCP("gauss-solver")


def _json_safe(obj):
    """Recursively converts numpy types and float nan/inf/NA values to JSON-safe primitives."""
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_json_safe(v) for v in obj]

    if hasattr(obj, "item") and callable(getattr(obj, "item", None)):
        try:
            obj = obj.item()
        except Exception:
            pass

    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj

    if obj is None or obj is pd.NA or obj is pd.NaT:
        return None

    try:
        if pd.isna(obj):
            return None
    except Exception:
        pass

    return obj


@mcp.tool()
def search_datasets(query: str) -> list[dict]:
    """Search for datasets matching the query.

    Loads the metadata catalog and matches query against categories, synonyms, and descriptions.
    """
    metadata = catalog.load_metadata()
    matches = catalog.search_datasets(query, metadata)
    return _json_safe([m.model_dump() for m in matches])


@mcp.tool()
def load_data(categories: list[str], required_columns: dict[str, list[str]]) -> dict:
    """Load requested datasets and return a coverage report with a unique dataset handle.

    Note that the loaded DataFrames never leave the server.
    """
    metadata = catalog.load_metadata()
    report = catalog.load_data(categories, required_columns, metadata)
    return _json_safe(report.model_dump())


@mcp.tool()
def clean_systematic(handle: str) -> dict:
    """Apply systematic cleaning rules on the loaded datasets under handle."""
    metadata = catalog.load_metadata()
    report = cleaning.clean_systematic(handle, metadata)
    return _json_safe(report.model_dump())


@mcp.tool()
def query_data(
    handle: str,
    category: str,
    expr: str | None = None,
    columns: list[str] | None = None,
    agg: str = "sample",
    limit: int = 20,
) -> dict:
    """Safely query and aggregate dataset columns using expression filtering."""
    report = safe_ops.query_data(
        handle=handle,
        category=category,
        expr=expr,
        columns=columns,
        agg=agg,
        limit=limit,
    )
    return _json_safe(report.model_dump())


@mcp.tool()
def clean_dynamic(handle: str, ops: list[dict], rationale: str = "") -> dict:
    """Safely apply a list of declarative CleanOps on stored DataFrames under handle."""
    report = safe_ops.clean_dynamic(handle=handle, ops=ops, rationale=rationale)
    return _json_safe(report.model_dump())


@mcp.tool()
def prefilter(handle: str, constraints: list[dict]) -> dict:
    """Safely pre-filter DataFrames using literal constraint boundaries."""
    report = prefilter_mod.prefilter(handle=handle, constraints=constraints)
    return _json_safe(report.model_dump())


@mcp.tool()
def solve_build(handle: str, pivot_schema: dict) -> dict:
    """Solve the PC build optimization problem using CP-SAT."""
    report = cpsat.solve_build(handle=handle, pivot_schema=pivot_schema)
    return _json_safe(report.model_dump())
