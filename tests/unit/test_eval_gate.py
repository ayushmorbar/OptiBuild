"""The eval suite is admin-gated: it must refuse to run without GAUSS_EVAL_ENABLED=1."""

import pytest

from scripts.run_eval import require_admin_gate


def test_eval_refused_without_env_var(monkeypatch):
    monkeypatch.delenv("GAUSS_EVAL_ENABLED", raising=False)
    with pytest.raises(SystemExit) as exc:
        require_admin_gate()
    assert "DISABLED" in str(exc.value)


def test_eval_refused_with_wrong_value(monkeypatch):
    monkeypatch.setenv("GAUSS_EVAL_ENABLED", "true")  # must be exactly "1"
    with pytest.raises(SystemExit):
        require_admin_gate()


def test_eval_allowed_when_enabled(monkeypatch):
    monkeypatch.setenv("GAUSS_EVAL_ENABLED", "1")
    require_admin_gate()  # no exit
