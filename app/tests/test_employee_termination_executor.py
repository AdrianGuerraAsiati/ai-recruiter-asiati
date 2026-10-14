"""Executor gating tests: no Odoo or Cognito side effects."""
import pytest

from app.domains.employees.termination import TerminationError
from app.domains.employees.termination_executor import execute_termination


def test_execution_is_disabled_without_explicit_opt_in(monkeypatch):
    monkeypatch.delenv("EMPLOYEE_TERMINATION_EXECUTION_ENABLED", raising=False)
    with pytest.raises(TerminationError, match="deshabilitada"):
        execute_termination(None, request_id="sample", odoo_client=None, cognito_client=None)


def test_execution_refuses_production_even_with_feature_flag(monkeypatch):
    monkeypatch.setenv("EMPLOYEE_TERMINATION_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(TerminationError, match="staging"):
        execute_termination(None, request_id="sample", odoo_client=None, cognito_client=None)
