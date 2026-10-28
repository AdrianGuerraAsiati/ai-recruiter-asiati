"""Production target selection safety contracts."""
from types import SimpleNamespace
import pytest
from app.domains.employee_documents import sign_target

def test_default_is_staging(monkeypatch):
    monkeypatch.delenv("ODOO_SIGN_TARGET", raising=False)
    assert sign_target.environment() == "staging"

def test_production_disabled_without_both_flags(monkeypatch):
    monkeypatch.setenv("ODOO_SIGN_TARGET", "production")
    monkeypatch.setenv("ODOO_SIGN_PRODUCTION_SEND_ENABLED", "true")
    monkeypatch.delenv("ODOO_SIGN_PRODUCTION_ENABLED", raising=False)
    assert sign_target.enabled("send") is False

def test_old_staging_record_cannot_reuse_production_id(monkeypatch):
    monkeypatch.setenv("ODOO_SIGN_TARGET", "production")
    obj = SimpleNamespace(odoo_sign_environment="staging",
        odoo_sign_template_id=100, odoo_sign_status="PREPARED",
        odoo_sign_request_id=None)
    with pytest.raises(sign_target.OdooSignTargetError):
        sign_target.assert_document_origin(obj)

@pytest.mark.parametrize("url", [
    "http://example.com", "https://asiati-test160526-39554181.dev.odoo.com",
])
def test_rejects_test_host(monkeypatch, url):
    monkeypatch.setattr(sign_target, "get_odoo_settings",
        lambda: SimpleNamespace(enabled=True, configured=True,
            base_url=url, database="prod", secret_id="/ai-recruiter/prod/odoo"))
    with pytest.raises(sign_target.OdooSignTargetError):
        sign_target.production_settings()
