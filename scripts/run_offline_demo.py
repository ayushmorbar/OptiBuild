"""Offline end-to-end demo: full solver pipeline with a HAND-BUILT PivotSchema (zero LLM calls).

This drives the entire deterministic engine (load -> gates -> clean -> prefilter -> CP-SAT)
without any Gemini call, so it works regardless of API quota.
"""

import json

from app.mcp_server.server import _json_safe
from app.schema import SolverRequest
from solver_app.pipeline import run_solver_pipeline

CATEGORIES = [
    "cpu",
    "cpu-cooler",
    "motherboard",
    "memory",
    "internal-hard-drive",
    "video-card",
    "case",
    "power-supply",
]


def main():
    pivot = {
        "user_intent": "cheapest complete PC build under $1500",
        "decision_variables": [
            {
                "category": c,
                "required_attributes": [
                    {"name": "name", "data_type": "str"},
                    {"name": "price", "data_type": "float"},
                ],
                "optional": False,
            }
            for c in CATEGORIES
        ],
        "derived_variables": [
            {
                "name": "total_price",
                "formula": "sum(" + ", ".join(f"{c}.price" for c in CATEGORIES) + ")",
                "dependencies": CATEGORIES,
            }
        ],
        "objectives": [
            {
                "target_variable": "total_price",
                "direction": "minimize",
                "weight": 1.0,
                "rationale": "cheapest complete build",
            }
        ],
        "constraints": [
            {
                "name": "budget_cap",
                "left_side": "total_price",
                "operator": "<=",
                "right_side": {"kind": "literal", "value": 1500},
                "is_hard": True,
                "origin": "user_explicit",
            }
        ],
    }

    request = SolverRequest(
        transaction_id="offline-demo",
        iteration=1,
        pivot_schema=pivot,
        context={
            "original_prompt": "cheapest complete PC under $1500",
            "locale_currency": "USD",
        },
    )

    print("Running the full solver pipeline OFFLINE (no LLM)...")
    response = run_solver_pipeline(request)
    print("\n--- Solver Response ---")
    print(json.dumps(_json_safe(response.model_dump()), indent=2))


if __name__ == "__main__":
    main()
