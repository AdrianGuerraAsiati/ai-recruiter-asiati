"""Synthetic Odoo tests: close, archive, retry after lost acknowledgement."""
from datetime import date
import pytest
from app.domains.employees.termination import TerminationError
from app.domains.odoo_sync.termination_delivery import close_contract_and_archive


class SyntheticOdoo:
    def __init__(self):
        self.employee = {"id": 42, "active": True}
        self.contracts = [{"id": 17, "employee_id": [42, "Synthetic"],
                           "state": "open", "date_end": False}]
        self.calls = []
        self.fail_after_contract_write = False

    def fields_get(self, model, **kwargs):
        if model == "hr.employee":
            return {"active": {"readonly": False}}
        return {"employee_id": {"readonly": False},
                "date_end": {"readonly": False},
                "state": {"readonly": False,
                          "selection": [("open", "Running"), ("close", "Expired")]}}

    def search_read(self, model, domain, **kwargs):
        if model == "hr.employee":
            if not self.employee["active"] and not kwargs.get("context", {}).get("active_test") is False:
                return []
            return [dict(self.employee)]
        return [dict(c) for c in self.contracts]

    def write(self, model, ids, values):
        self.calls.append((model, tuple(ids), dict(values)))
        if model == "hr.contract":
            self.contracts[0].update(values)
            if self.fail_after_contract_write:
                self.fail_after_contract_write = False
                raise RuntimeError("connection dropped after Odoo accepted write")
        if model == "hr.employee":
            self.employee.update(values)
        return True


def test_closes_and_archives_once():
    client = SyntheticOdoo()
    outcome = close_contract_and_archive(client, employee_odoo_id="42",
                                         effective_date=date(2026, 10, 14))
    assert outcome["odoo_closed"] and outcome["odoo_archived"]
    assert client.contracts[0]["date_end"] == "2026-10-14"
    assert client.employee["active"] is False
    close_contract_and_archive(client, employee_odoo_id="42",
                               effective_date=date(2026, 10, 14))
    assert len(client.calls) == 2
    assert client.employee["active"] is False


def test_retry_after_unknown_odoo_acknowledgement():
    client = SyntheticOdoo()
    client.fail_after_contract_write = True
    with pytest.raises(RuntimeError):
        close_contract_and_archive(client, employee_odoo_id="42",
                                   effective_date=date(2026, 10, 14))
    close_contract_and_archive(client, employee_odoo_id="42",
                               effective_date=date(2026, 10, 14))
    assert [m for m, _, _ in client.calls].count("hr.contract") == 1
    assert client.employee["active"] is False


def test_rejects_contract_with_wrong_employee_without_writes():
    client = SyntheticOdoo()
    client.contracts[0]["employee_id"] = [99, "Someone Else"]
    with pytest.raises(TerminationError):
        close_contract_and_archive(client, employee_odoo_id="42",
                                   effective_date=date(2026, 10, 14))
    assert client.calls == []


def test_rejects_unrecognized_state_selection():
    client = SyntheticOdoo()
    original = client.fields_get
    def changed(model, **kwargs):
        values = original(model, **kwargs)
        if model == "hr.contract":
            values["state"]["selection"] = [("open", "Running")]
        return values
    client.fields_get = changed
    with pytest.raises(TerminationError, match="close"):
        close_contract_and_archive(client, employee_odoo_id="42",
                                   effective_date=date(2026, 10, 14))
    assert client.calls == []
