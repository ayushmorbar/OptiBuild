"""Integration tests for the deterministic Solver pipeline scenarios."""

from pathlib import Path

import pytest

from app.schema import SolverRequest
from solver_app.pipeline import run_solver_pipeline


@pytest.mark.skipif(
    not Path("data/pc-csv/cpu.csv").exists(),
    reason="raw CSVs absent (expected in local dev clone only)",
)
def test_solver_pipeline_scenarios():
    # 1. Generous budget case -> SUCCESS
    request_data_success = {
        "transaction_id": "tx-12345",
        "iteration": 1,
        "context": {
            "original_prompt": "Build a cheap PC",
            "locale_currency": "USD",
        },
        "pivot_schema": {
            "schema_version": "1.0",
            "user_intent": "Build cheapest PC under $2000",
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

    req_success = SolverRequest.model_validate(request_data_success)
    res_success = run_solver_pipeline(req_success)

    assert res_success.status == "SUCCESS"
    assert res_success.transaction_id == "tx-12345"
    assert "cpu" in res_success.result.selections
    assert "memory" in res_success.result.selections
    assert "total_price" in res_success.result.derived_values
    assert len(res_success.result.objective_report) == 1

    # 2. Insufficient budget cap ($1) -> INFEASIBLE
    request_data_infeasible = request_data_success.copy()
    request_data_infeasible["pivot_schema"] = request_data_success[
        "pivot_schema"
    ].copy()
    request_data_infeasible["pivot_schema"]["constraints"] = [
        {
            "name": "budget_cap",
            "left_side": "total_price",
            "operator": "<=",
            "right_side": {"kind": "literal", "value": 1.0},
            "is_hard": True,
            "origin": "user_explicit",
        }
    ]

    req_infeasible = SolverRequest.model_validate(request_data_infeasible)
    res_infeasible = run_solver_pipeline(req_infeasible)

    assert res_infeasible.status == "INFEASIBLE"
    assert res_infeasible.feedback is not None
    assert len(res_infeasible.feedback.relaxation_suggestions) > 0
    assert res_infeasible.feedback.relaxation_suggestions[0].constraint == "budget_cap"

    # 3. Non-existent category -> MISSING_DATA
    request_data_missing = request_data_success.copy()
    request_data_missing["pivot_schema"] = request_data_success["pivot_schema"].copy()
    request_data_missing["pivot_schema"]["decision_variables"] = [
        {
            "category": "cpu",
            "required_attributes": [{"name": "price", "data_type": "float"}],
            "optional": False,
        },
        {
            "category": "nonexistent",
            "required_attributes": [{"name": "price", "data_type": "float"}],
            "optional": False,
        },
    ]
    request_data_missing["pivot_schema"]["derived_variables"] = [
        {
            "name": "total_price",
            "formula": "sum(cpu.price, nonexistent.price)",
            "dependencies": ["cpu", "nonexistent"],
        }
    ]

    req_missing = SolverRequest.model_validate(request_data_missing)
    res_missing = run_solver_pipeline(req_missing)

    assert res_missing.status == "MISSING_DATA"
    assert res_missing.feedback is not None
    assert len(res_missing.feedback.missing_attributes) > 0
    assert res_missing.feedback.missing_attributes[0].category == "nonexistent"
