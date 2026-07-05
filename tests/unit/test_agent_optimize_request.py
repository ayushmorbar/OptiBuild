"""Unit tests for the optimize_request tool in app/agent.py."""

from unittest.mock import patch

from app.agent import optimize_request


def test_optimize_request_success():
    """Verify optimize_request successfully returns the dict from concierge_runner.run."""
    mock_result = {
        "status": "SUCCESS",
        "solver_response": {"status": "SUCCESS"},
        "schema": {},
        "iterations": 1,
    }

    with patch("app.concierge_runner.run", return_value=mock_result) as mock_run:
        res = optimize_request("Build a gaming PC")
        mock_run.assert_called_once_with("Build a gaming PC")
        assert res == mock_result


def test_optimize_request_needs_clarification():
    """Verify optimize_request successfully returns the dict from concierge_runner.run when clarification is needed."""
    mock_result = {
        "status": "NEEDS_CLARIFICATION",
        "schema": {},
        "questions": ["What is your budget?"],
        "iterations": 3,
    }

    with patch("app.concierge_runner.run", return_value=mock_result) as mock_run:
        res = optimize_request("Build a PC")
        mock_run.assert_called_once_with("Build a PC")
        assert res == mock_result


def test_optimize_request_error_handling():
    """Verify optimize_request catches exceptions and returns an ERROR dict."""
    with patch("app.concierge_runner.run", side_effect=ValueError("Pipeline failure")):
        res = optimize_request("Build a PC")
        assert res == {
            "status": "ERROR",
            "error": "Pipeline failure",
        }
