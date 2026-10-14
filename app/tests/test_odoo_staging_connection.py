"""Odoo staging must remain isolated from production."""
import pytest

from app.domains.odoo_sync.integration import OdooNotConfigured
from app.domains.odoo_sync.staging import staging_settings, build_staging_client


@pytest.fixture(autouse=True)
def production_env(monkeypatch):
    monkeypatch.setenv("ODOO_BASE_URL", "https://production.example.com")
    monkeypatch.setenv("ODOO_DATABASE", "production_db")
    monkeypatch.setenv("ODOO_USERNAME", "prod@example.com")
    monkeypatch.setenv("ODOO_SECRET_ID", "/ai-recruiter/prod/odoo")
    monkeypatch.setenv("ODOO_STAGING_BASE_URL", "https://staging.example.com")
    monkeypatch.setenv("ODOO_STAGING_DATABASE", "staging_db")
    monkeypatch.setenv("ODOO_STAGING_USERNAME", "test@example.com")
    monkeypatch.setenv("ODOO_STAGING_SECRET_ID", "/ai-recruiter/staging/odoo")


def test_staging_has_separate_settings():
    config = staging_settings()
    assert config.enabled
    assert config.database == "staging_db"
    assert config.secret_id == "/ai-recruiter/staging/odoo"


@pytest.mark.parametrize("variable,value", [
    ("ODOO_STAGING_BASE_URL", "https://production.example.com"),
    ("ODOO_STAGING_DATABASE", "production_db"),
    ("ODOO_STAGING_SECRET_ID", "/ai-recruiter/prod/odoo"),
    ("ODOO_STAGING_BASE_URL", "http://staging.example.com"),
    ("ODOO_STAGING_SECRET_ID", ""),
])
def test_rejects_production_reuse_and_missing_configuration(monkeypatch, variable, value):
    monkeypatch.setenv(variable, value)
    with pytest.raises(OdooNotConfigured):
        staging_settings()


def test_credential_isolation(monkeypatch):
    class FakeSecret:
        def read(self):
            return {"api_key": "synthetic-staging-key"}

    class FakeProxy:
        def __init__(self, url, **kwargs):
            pass

    client = build_staging_client(secret_store=FakeSecret(), proxy_factory=FakeProxy)
    assert client.database == "staging_db"
    assert client.username == "test@example.com"
    assert client.base_url == "https://staging.example.com"
