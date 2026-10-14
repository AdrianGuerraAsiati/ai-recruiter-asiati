"""Contract termination safety tests; no real employee/contract writes."""
from datetime import date, timedelta

import pytest

from app.domains.employees.termination import (
    TerminationError,
    TerminationReason,
    build_termination_plan,
)


def payload():
    return dict(
        employee_id="local-123",
        odoo_employee_id="99",
        effective_date=date(2026, 10, 14),
        reason=TerminationReason.RESIGNATION,
        notes="Renuncia voluntaria registrada por Talento Humano.",
        today=date(2026, 10, 14),
    )


def test_plans_preserve_employee_and_revoke_access_only_after_odoo():
    plan = build_termination_plan(**payload())
    assert plan.odoo_employee_id == "99"
    assert "delete_employee" not in plan.steps
    assert "archive_odoo_employee" in plan.steps
    assert plan.steps.index("close_contracts_in_odoo") < plan.steps.index("disable_cognito_access")


@pytest.mark.parametrize(
    "overrides",
    [
        {"odoo_employee_id": None},
        {"already_terminated": True},
        {"effective_date": date(2026, 10, 15)},
        {"notes": "corto"},
        {"reason": "INVALID"},
        {"employee_id": ""},
    ],
)
def test_rejects_unsafe_requests(overrides):
    with pytest.raises(TerminationError):
        build_termination_plan(**(payload() | overrides))


def test_reason_is_strict_enum():
    assert {reason.value for reason in TerminationReason} == {
        "RESIGNATION", "CONTRACT_END", "DISMISSAL", "MUTUAL_AGREEMENT", "OTHER"
    }


@pytest.mark.parametrize("overrides", [
    {"employee_id": "  "},
    {"odoo_employee_id": "   "},
    {"effective_date": None},
    {"effective_date": "2026-10-14"},
    {"notes": ""},
    {"notes": None},
    {"notes": "x" * 2001},
])
def test_invalid_termination_payloads_are_rejected(overrides):
    with pytest.raises(TerminationError):
        build_termination_plan(**(payload() | overrides))


def test_plan_normalizes_whitespace():
    result = build_termination_plan(**(payload() | {
        "employee_id": " local-123 ",
        "odoo_employee_id": " 99 ",
        "notes": "   Renuncia voluntaria documentada.   ",
    }))
    assert result.employee_id == "local-123"
    assert result.odoo_employee_id == "99"
    assert result.notes == "Renuncia voluntaria documentada."
