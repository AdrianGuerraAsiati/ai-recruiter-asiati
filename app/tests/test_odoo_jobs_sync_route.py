"""Route-level tests for explicit Odoo vacancy reconciliation."""

import pytest
from fastapi import HTTPException

from app.domains.odoo_sync import router


def test_sync_jobs_to_odoo_returns_reconciliation_summary(monkeypatch):
    expected = {
        "total": 18,
        "active_total": 18,
        "paused_total": 0,
        "attempted": 18,
        "synced": 18,
        "failed": 0,
        "skipped": 0,
    }
    monkeypatch.setattr(
        router.job_delivery,
        "sync_all_jobs_now",
        lambda db: expected,
    )

    assert router.sync_jobs_to_odoo(db=object(), _principal={"sub": "admin"}) == expected


def test_sync_jobs_to_odoo_translates_delivery_failure(monkeypatch):
    def fail(_db):
        raise router.job_delivery.OdooJobDeliveryError("transport failed")

    monkeypatch.setattr(router.job_delivery, "sync_all_jobs_now", fail)

    with pytest.raises(HTTPException) as exc:
        router.sync_jobs_to_odoo(db=object(), _principal={"sub": "admin"})

    assert exc.value.status_code == 502
    assert "transport failed" in str(exc.value.detail)
