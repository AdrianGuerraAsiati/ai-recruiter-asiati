"""Odoo diagnostics expose the vacancy model used by Talent publication."""

from app.domains.odoo_sync import router


class FakeDiagnosticsClient:
    def healthcheck(self):
        return {"connected": True, "uid": 99}

    def fields_get(self, model):
        return {
            "name": {"type": "char"},
            "website_published": {"type": "boolean"},
        }


def test_diagnostics_include_hr_job_capabilities(monkeypatch):
    monkeypatch.setattr(
        router.integration,
        "connection_status",
        lambda: {"enabled": True, "configured": True},
    )
    monkeypatch.setattr(
        router.integration,
        "build_odoo_client",
        lambda: FakeDiagnosticsClient(),
    )

    result = router.odoo_readonly_diagnostics(_principal={})

    assert result["models"]["hr.job"]["available"] is True
    assert "website_published" in result["models"]["hr.job"]["fields"]
