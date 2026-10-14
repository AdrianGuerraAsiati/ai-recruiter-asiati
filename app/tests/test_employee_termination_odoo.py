"""Read-only Odoo termination checks must never mutate records."""
from datetime import date
import pytest

from app.domains.employees.termination import TerminationError
from app.domains.odoo_sync.employee_termination import close_odoo_employment


class FakeOdoo:
    def __init__(self, *, contracts=None, employee=None):
        self.contracts = contracts if contracts is not None else [
            {"id": 17, "employee_id": [42, "Synthetic"], "date_end": False, "state": "open"}
        ]
        self.employee = employee if employee is not None else [{"id": 42, "active": True}]
        self.writes = []

    def fields_get(self, model, **kwargs):
        if model == "hr.employee":
            return {"active": {"type": "boolean"}}
        return {
            "employee_id": {"readonly": False},
            "date_end": {"readonly": False},
            "state": {"readonly": False},
        }

    def search_read(self, model, *args, **kwargs):
        return self.employee if model == "hr.employee" else self.contracts

    def write(self, *args, **kwargs):
        self.writes.append((args, kwargs))
        raise AssertionError("Never mutate Odoo during preflight")


def test_preflight_inspects_unique_open_contract_without_writes():
    client = FakeOdoo()
    result = close_odoo_employment(client, employee_odoo_id="42", effective_date=date(2026, 10, 14))
    assert result["verified"] is True
    assert result["executed"] is False
    assert result["active_contract_ids"] == [17]
    assert client.writes == []


@pytest.mark.parametrize("changes", [
    {"employee": []},
    {"contracts": [
        {"id": 1, "state": "open"}, {"id": 2, "state": "open"}
    ]},
    {"contracts": [{"id": 1, "state": "draft"}]},
])
def test_ambiguous_or_missing_records_are_rejected(changes):
    client = FakeOdoo(**changes)
    with pytest.raises(TerminationError):
        close_odoo_employment(client, employee_odoo_id="42", effective_date=date(2026, 10, 14))
    assert client.writes == []


def test_invalid_external_id_does_not_contact_odoo():
    with pytest.raises(TerminationError):
        close_odoo_employment(FakeOdoo(), employee_odoo_id="unknown", effective_date=date(2026, 10, 14))
