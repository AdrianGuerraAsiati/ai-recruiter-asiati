"""Pure guardrail tests for the manual, external staging E2E entry point."""
from datetime import date, timedelta

import pytest

from app.scripts.verify_talent_staging_termination_e2e import (
    CognitoRecorder,
    OdooRecorder,
    _subject,
    require_safe_inputs,
)


def test_default_dry_run_does_not_need_confirmation():
    require_safe_inputs(
        employee_id=123, effective_date=date.today(),
        execute=False, confirmation="",
    )


@pytest.mark.parametrize("employee_id,execute,confirmation", [
    (0, False, ""),
    (-1, True, "EXECUTE-E2E-TERMINATION--1"),
    (123, True, ""),
    (123, True, "EXECUTE-E2E-TERMINATION-124"),
])
def test_write_rejected_without_exact_confirmation(employee_id, execute, confirmation):
    with pytest.raises(ValueError):
        require_safe_inputs(
            employee_id=employee_id, effective_date=date.today(),
            execute=execute, confirmation=confirmation,
        )


def test_future_termination_date_refused_even_in_dry_run():
    with pytest.raises(ValueError, match="invalid"):
        require_safe_inputs(
            employee_id=123, effective_date=date.today() + timedelta(days=1),
            execute=False, confirmation="",
        )


def test_explicit_confirmation_allows_valid_synthetic_input():
    require_safe_inputs(
        employee_id=123, effective_date=date.today(),
        execute=True, confirmation="EXECUTE-E2E-TERMINATION-123",
    )


def test_sub_is_unique_and_mandatory():
    assert _subject({"UserAttributes": [
        {"Name": "sub", "Value": "synthetic-staging-sub"}
    ]}) == "synthetic-staging-sub"
    for attrs in ([], [
        {"Name": "sub", "Value": "one"},
        {"Name": "sub", "Value": "two"},
    ], [{"Name": "sub", "Value": ""}]):
        with pytest.raises(ValueError):
            _subject({"UserAttributes": attrs})


def test_read_only_recorders_never_call_write_or_disable():
    class Odoo:
        database = "isolated"
        base_url = "https://test.example.invalid"
        def __init__(self):
            self.writes = []
        def write(self, model, ids, values):
            self.writes.append((model, ids, values))
            return True
        def search_read(self, *args, **kwargs):
            return [{"id": 1}]

    class Cognito:
        def __init__(self):
            self.calls = []
        def admin_get_user(self, **kwargs):
            return {"Enabled": True}
        def admin_disable_user(self, **kwargs):
            self.calls.append(kwargs)
            return {}

    inner_o = Odoo()
    inner_c = Cognito()
    odoo = OdooRecorder(inner_o)
    cognito = CognitoRecorder(inner_c)
    assert odoo.search_read("hr.employee", [], limit=1) == [{"id": 1}]
    assert cognito.admin_get_user(UserPoolId="stage", Username="synthetic")["Enabled"]
    assert odoo.writes == []
    assert cognito.disable_calls == 0
    assert inner_c.calls == []
