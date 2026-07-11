"""Unit tests for the imposed safety gate (app/safety.py)."""

import logging
from unittest.mock import MagicMock, patch

from app.safety import SafetyVerdict, build_safety_instruction, make_safety_checker


def _client_returning(parsed=None, text=""):
    """Fake genai client whose generate_content returns a canned response."""
    client = MagicMock()
    response = MagicMock()
    response.parsed = parsed
    response.text = text
    client.models.generate_content.return_value = response
    return client


def test_checker_fail_open_on_client_error(caplog):
    with patch("app.safety.genai.Client", side_effect=RuntimeError("no key")):
        check = make_safety_checker()
        with caplog.at_level(logging.WARNING, logger="app.safety"):
            assert check("anything") == (True, None)
    assert "fail-open" in caplog.text


def test_checker_fail_open_on_parse_error():
    client = _client_returning(parsed=None, text="not json")
    with patch("app.safety.genai.Client", return_value=client):
        check = make_safety_checker()
        assert check("cheap pc") == (True, None)


def test_checker_passes_on_safe_verdict():
    client = _client_returning(parsed=SafetyVerdict(safe=True))
    with patch("app.safety.genai.Client", return_value=client):
        check = make_safety_checker()
        assert check("cheap pc under $1500") == (True, None)


def test_checker_refuses_on_unsafe_verdict():
    client = _client_returning(parsed=SafetyVerdict(safe=False, reason="illegal"))
    with patch("app.safety.genai.Client", return_value=client):
        check = make_safety_checker()
        assert check("crack licensed software") == (False, "illegal")


def test_refusal_with_empty_reason_gets_fallback():
    client = _client_returning(parsed=SafetyVerdict(safe=False, reason=None))
    with patch("app.safety.genai.Client", return_value=client):
        check = make_safety_checker()
        safe, reason = check("bad request")
    assert safe is False
    assert reason == "This request cannot be processed."


def test_instruction_appends_pack_safety_notes():
    fake_domain = MagicMock()
    fake_domain.safety_notes = ["note-x"]
    with (
        patch("app.mcp_server.catalog.load_metadata", return_value={}),
        patch("app.mcp_server.catalog.get_domain_context", return_value=fake_domain),
    ):
        instruction = build_safety_instruction()
    assert "- note-x" in instruction


def test_instruction_survives_missing_pack():
    with patch("app.mcp_server.catalog.load_metadata", side_effect=OSError("no pack")):
        instruction = build_safety_instruction()
    assert "safety gate" in instruction
    assert "Additionally refuse" not in instruction
