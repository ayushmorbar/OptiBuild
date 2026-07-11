"""Unit tests for the optimize_request tool in app/agent.py."""

import json
from unittest.mock import patch

from app.agent import optimize_request
from app.schema import PivotSchema, SolverResponse

_SCHEMA = {
    "user_intent": "cheap pc",
    "decision_variables": [
        {
            "category": "cpu",
            "required_attributes": [{"name": "price", "data_type": "float"}],
        }
    ],
    "objectives": [{"target_variable": "cpu.price", "direction": "minimize"}],
}


def test_optimize_request_success_returns_lean_json_safe_view():
    """The tool must strip the internal schema/trace and be JSON-serializable."""
    solver_response = SolverResponse(
        transaction_id="t1",
        status="SUCCESS",
        result={
            "selections": {"cpu": {"name": "X", "price": 42.0}},
            "derived_values": {"total_price": 42.0},
            "objective_report": [
                {"target": "cpu.price", "direction": "minimize", "value": 42.0}
            ],
        },
        trace={
            "category_resolution": {"processor": "cpu"},
            "rows_after_prefilter": {"cpu": 84},  # internals, not for the LLM
        },
    )
    rich_result = {
        "status": "SUCCESS",
        "solver_response": solver_response,  # Pydantic object, as run_concierge returns
        "schema": PivotSchema.model_validate(_SCHEMA),  # must NOT reach the LLM
        "iterations": 1,
    }

    with patch("app.concierge_runner.run", return_value=rich_result) as mock_run:
        res = optimize_request("Build a gaming PC")
        mock_run.assert_called_once_with("Build a gaming PC")

    json.dumps(res)  # JSON-safe end to end
    assert res["status"] == "SUCCESS"
    assert "schema" not in res  # internal contract stripped
    sr = res["solver_response"]
    assert sr["result"]["selections"]["cpu"]["name"] == "X"
    assert sr["category_resolution"] == {"processor": "cpu"}
    assert "trace" not in sr  # solver internals stripped


def test_optimize_request_needs_clarification():
    rich_result = {
        "status": "NEEDS_CLARIFICATION",
        "schema": None,
        "questions": ["What is your budget?"],
        "iterations": 3,
    }

    with patch("app.concierge_runner.run", return_value=rich_result):
        res = optimize_request("Build a PC")

    assert res["status"] == "NEEDS_CLARIFICATION"
    assert res["questions"] == ["What is your budget?"]
    assert res["iterations"] == 3
    assert "schema" not in res


def test_optimize_request_refused_passthrough():
    """A safety-gate refusal must reach the root agent unchanged and JSON-safe."""
    rich_result = {
        "status": "REFUSED",
        "questions": ["Refused: illegal activity."],
        "iterations": 0,
    }

    with patch("app.concierge_runner.run", return_value=rich_result):
        res = optimize_request("crack licensed software")

    json.dumps(res)
    assert res["status"] == "REFUSED"
    assert res["questions"] == ["Refused: illegal activity."]
    assert res["iterations"] == 0
    assert "schema" not in res


def test_optimize_request_error_handling():
    with patch("app.concierge_runner.run", side_effect=ValueError("Pipeline failure")):
        res = optimize_request("Build a PC")
        assert res == {
            "status": "ERROR",
            "error": "Pipeline failure",
        }
