"""Unit tests for app/agent.py helper utilities."""

from app.agent import redact_text, sanitize_budget


def test_sanitize_budget():
    assert sanitize_budget("$1400") == 1400.0
    assert sanitize_budget("1200.50 USD") == 1200.50
    assert sanitize_budget("1500") == 1500.0
    assert sanitize_budget("invalid") == 0.0
    assert sanitize_budget("") == 0.0


def test_redact_pii():
    text_with_cc = (
        "My credit card number is 1234-5678-1234-5678 and my SSN is 000-12-3456."
    )
    redacted = redact_text(text_with_cc)
    assert "1234-5678-1234-5678" not in redacted
    assert "000-12-3456" not in redacted
    assert "[REDACTED CREDIT CARD]" in redacted
    assert "[REDACTED PII]" in redacted
