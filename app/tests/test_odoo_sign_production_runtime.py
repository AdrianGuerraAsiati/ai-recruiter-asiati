"""Prevent production Odoo from reusing legacy staging document references."""
from types import SimpleNamespace
import pytest

from app.domains.employee_documents import sign_runtime


def test_legacy_contract_cannot_reuse_test_ids():
    row = SimpleNamespace(odoo_sign_environment="staging",
                          odoo_sign_template_id=128,
                          odoo_sign_status="PREPARED", odoo_sign_request_id=140)
    with pytest.raises(sign_runtime.ProductionSignUnavailable):
        sign_runtime.assert_origin(row)


def test_new_contract_may_prepare_only_without_prior_remote_ids():
    row = SimpleNamespace(odoo_sign_environment=None,
                          odoo_sign_template_id=None,
                          odoo_sign_status="NOT_PREPARED", odoo_sign_request_id=None)
    sign_runtime.assert_origin(row, new=True)
    with pytest.raises(sign_runtime.ProductionSignUnavailable):
        sign_runtime.assert_origin(row)


@pytest.mark.parametrize("url", [
    "http://odoo.asiaticorp.com",
    "https://asiati-test160526-39554181.dev.odoo.com",
])
def test_never_route_signing_to_test(monkeypatch, url):
    monkeypatch.setattr(sign_runtime, "get_odoo_settings", lambda: SimpleNamespace(
        enabled=True, configured=True, base_url=url, database="production",
        secret_id="/ai-recruiter/prod/odoo"
    ))
    with pytest.raises(sign_runtime.ProductionSignUnavailable):
        sign_runtime.settings()


def test_prod_disabled_until_runtime_enabled(monkeypatch):
    monkeypatch.delenv("ODOO_SIGN_PRODUCTION_ENABLED", raising=False)
    assert not sign_runtime.enabled()
