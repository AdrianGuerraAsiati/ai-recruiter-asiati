"""No unintended Odoo writes in the staging E2E runner preflight."""
from datetime import date
from types import SimpleNamespace

import pytest

from app.scripts import verify_odoo_staging_termination_e2e as e2e


class FakeStaging:
    def __init__(self, name="TALENT-E2E-TERMINATION-SAMPLE", state="open"):
        self.name = name
        self.state = state
        self.writes = []

    def healthcheck(self):
        return {"connected": True, "uid": 97}

    def search_read(self, model, domain, **kwargs):
        if model == "hr.employee":
            return [{"id": 42, "name": self.name, "active": True}]
        return [{"id": 11, "state": self.state, "date_end": False,
                 "employee_id": [42, "Synthetic"]}]


def setup(monkeypatch, client):
    monkeypatch.setattr(e2e, "staging_settings", lambda: SimpleNamespace(
        base_url="https://" + e2e.HOST, database=e2e.DATABASE))
    monkeypatch.setattr(e2e, "build_staging_client", lambda: client)
    monkeypatch.delenv("EMPLOYEE_TERMINATION_EXECUTION_ENABLED", raising=False)


def test_dry_run_never_calls_delivery(monkeypatch):
    client = FakeStaging()
    setup(monkeypatch, client)
    monkeypatch.setattr(e2e, "close_contract_and_archive",
                        lambda *a, **k: pytest.fail("unexpected write"))
    result = e2e.run(employee_id=42, effective_date=date(2026, 10, 14),
                     execute=False, confirm="")
    assert result["mode"] == "DRY_RUN"
    assert result["would_write"]


def test_rejects_real_employee(monkeypatch):
    setup(monkeypatch, FakeStaging(name="Real Employee"))
    with pytest.raises(ValueError, match="synthetic"):
        e2e.run(employee_id=42, effective_date=date(2026, 10, 14),
                execute=True, confirm="TALENT-E2E-TERMINATION-42")


def test_rejects_unconfirmed_execution(monkeypatch):
    setup(monkeypatch, FakeStaging())
    with pytest.raises(ValueError, match="confirmation"):
        e2e.run(employee_id=42, effective_date=date(2026, 10, 14),
                execute=True, confirm="")


def test_rejects_prod_execution_flag(monkeypatch):
    setup(monkeypatch, FakeStaging())
    monkeypatch.setenv("EMPLOYEE_TERMINATION_EXECUTION_ENABLED", "true")
    with pytest.raises(ValueError, match="disabled"):
        e2e.run(employee_id=42, effective_date=date(2026, 10, 14),
                execute=False, confirm="")
