"""Scripted demonstration run of the Solver Specialist."""

import json
import uuid

from solver_app.agent import solve


def main():
    # Build a valid, generous SolverRequest payload dict
    request_dict = {
        "transaction_id": str(uuid.uuid4()),
        "iteration": 1,
        "context": {
            "original_prompt": "Build a budget gaming PC",
            "locale_currency": "USD",
        },
        "pivot_schema": {
            "schema_version": "1.0",
            "user_intent": "Build cheapest PC under $2000 budget cap",
            "decision_variables": [
                {
                    "category": "cpu",
                    "required_attributes": [{"name": "price", "data_type": "float"}],
                    "optional": False,
                },
                {
                    "category": "memory",
                    "required_attributes": [{"name": "price", "data_type": "float"}],
                    "optional": False,
                },
            ],
            "derived_variables": [
                {
                    "name": "total_price",
                    "formula": "sum(cpu.price, memory.price)",
                    "dependencies": ["cpu", "memory"],
                }
            ],
            "objectives": [
                {
                    "target_variable": "total_price",
                    "direction": "minimize",
                }
            ],
            "constraints": [
                {
                    "name": "budget_cap",
                    "left_side": "total_price",
                    "operator": "<=",
                    "right_side": {"kind": "literal", "value": 2000.0},
                    "is_hard": True,
                    "origin": "user_explicit",
                }
            ],
        },
    }

    print("Running solve() with generous budget...")
    response = solve(request_dict)
    print("\n--- SolverResponse ---")
    print(json.dumps(response, indent=2))


if __name__ == "__main__":
    main()
