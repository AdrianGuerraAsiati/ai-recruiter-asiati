"""Read-only staging preflight uses only synthetic environment settings."""
from types import SimpleNamespace

from app.domains.odoo_sync import staging as odoo_staging
from app.scripts.termination_staging_preflight import checks


def configure(monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("EMPLOYEE_TERMINATION_EXECUTION_ENABLED", "true")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://synthetic:synthetic@127.0.0.1:5432/talent_e2e_terminations",
    )
    monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-east-2_production")
    monkeypatch.setenv("COGNITO_STAGING_USER_POOL_ID", "us-east-2_k6Q52r2rR")
    monkeypatch.setattr(
        odoo_staging,
        "staging_settings",
        lambda: SimpleNamespace(
            base_url="https://asiati-test160526-39554181.dev.odoo.com",
            database="asiati-test160526-39554181",
        ),
    )


def test_preflight_ready_only_with_dedicated_endpoints(monkeypatch):
    configure(monkeypatch)
    result = checks()
    assert all(result.values())


def test_preflight_rejects_production_database(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", "postgresql://synthetic:synthetic@localhost/ai_recruiter")
    result = checks()
    assert not result["talent_database_is_dedicated_postgres"]


def test_preflight_rejects_missing_database_url(monkeypatch):
    configure(monkeypatch)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    result = checks()
    assert not result["talent_database_is_dedicated_postgres"]


def test_preflight_rejects_other_cognito_pool(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setenv("COGNITO_STAGING_USER_POOL_ID", "us-east-2_anotherPool")
    result = checks()
    assert not result["cognito_uses_separate_pool"]


def test_preflight_rejects_prod_environment(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("EMPLOYEE_TERMINATION_EXECUTION_ENABLED", "false")
    result = checks()
    assert not result["app_environment_is_staging"]
    assert not result["termination_execution_opted_in"]
