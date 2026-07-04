"""Model Context Protocol (MCP) server for PC component optimization."""

from typing import List, Optional
from mcp.server.fastmcp import FastMCP
from app.tools import find_optimal_builds as solver_find_optimal_builds

mcp = FastMCP("pc_builder_solver")

@mcp.tool()
def find_optimal_builds(
    budget: float,
    purpose: str,
    cpu_brand: Optional[str] = None,
    gpu_brand: Optional[str] = None,
    form_factor: Optional[str] = None,
    cooling_type: Optional[str] = None,
    pre_owned_parts: Optional[List[str]] = None
) -> dict:
    """Finds up to 3 optimal, fully compatible PC configurations under a given budget.

    Args:
        budget: The maximum budget for the PC build in USD.
        purpose: The target usage of the PC (e.g., Gaming, AI training, Office).
        cpu_brand: Optional brand preference for CPU (e.g., AMD, Intel).
        gpu_brand: Optional brand preference for GPU (e.g., NVIDIA, AMD).
        form_factor: Optional size preference (e.g., ATX, Micro-ATX, Mini-ITX).
        cooling_type: Optional CPU cooler preference (e.g., air, liquid).
        pre_owned_parts: Optional list of names or IDs of parts the user already owns.

    Returns:
        A dictionary containing the list of configurations and count information.
    """
    return solver_find_optimal_builds(
        budget=budget,
        purpose=purpose,
        cpu_brand=cpu_brand,
        gpu_brand=gpu_brand,
        form_factor=form_factor,
        cooling_type=cooling_type,
        pre_owned_parts=pre_owned_parts
    )

if __name__ == "__main__":
    mcp.run()
