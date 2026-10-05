import app.config as config
from app.config import CORS_ORIGINS, api_docs_enabled, get_aws_region, get_database_url


def test_aws_region_defaults_to_us_east_2(monkeypatch):
    monkeypatch.delenv("AWS_REGION", raising=False)
    assert get_aws_region() == "us-east-2"


def test_aws_region_reads_existing_environment_name(monkeypatch):
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    assert get_aws_region() == "us-west-2"


def test_database_url_reads_existing_environment_name(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://example/test")
    assert get_database_url() == "postgresql://example/test"


def test_database_url_defaults_to_empty_string(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert get_database_url() == ""


def test_api_docs_default_to_enabled_for_local_development(monkeypatch):
    monkeypatch.delenv("API_DOCS_ENABLED", raising=False)
    assert api_docs_enabled() is True


def test_api_docs_can_be_disabled_for_production(monkeypatch):
    monkeypatch.setenv("API_DOCS_ENABLED", "false")
    assert api_docs_enabled() is False


def test_cors_origins_preserve_public_contract():
    assert CORS_ORIGINS == (
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        "https://ai.adrianguerra.net",
        "https://air.adrianguerra.net",
    )


def test_import_storage_and_queue_are_required(monkeypatch):
    monkeypatch.setenv("IMPORT_STAGING_BUCKET", "staging")
    monkeypatch.setenv("IMPORT_QUEUE_URL", "https://queue.example")
    assert config.get_import_staging_bucket() == "staging"
    assert config.get_import_queue_url() == "https://queue.example"


def test_import_worker_defaults(monkeypatch):
    monkeypatch.delenv("IMPORT_EVALUATION_CONCURRENCY", raising=False)
    monkeypatch.delenv("IMPORT_LEASE_TIMEOUT_SECONDS", raising=False)
    assert config.get_import_evaluation_concurrency() == 3
    assert config.get_import_lease_timeout_seconds() == 300


def test_import_worker_overrides(monkeypatch):
    monkeypatch.setenv("IMPORT_EVALUATION_CONCURRENCY", "5")
    monkeypatch.setenv("IMPORT_LEASE_TIMEOUT_SECONDS", "600")
    assert config.get_import_evaluation_concurrency() == 5
    assert config.get_import_lease_timeout_seconds() == 600


def test_gmail_settings_are_environment_driven_and_passwordless(monkeypatch):
    monkeypatch.setenv("GMAIL_ENABLED", "true")
    monkeypatch.setenv("GMAIL_CLIENT_ID", "personal-client-id")
    monkeypatch.setenv("GMAIL_CLIENT_SECRET", "personal-client-secret")
    monkeypatch.setenv("GMAIL_REFRESH_TOKEN", "personal-refresh-token")
    monkeypatch.setenv("GMAIL_USER_ID", "me")
    monkeypatch.setenv("GMAIL_QUERY", "label:inbox has:attachment")
    monkeypatch.setenv("GMAIL_ALLOWED_SENDERS", "indeed@example.com, jobs@example.net")

    settings = config.get_gmail_settings()

    assert settings.enabled is True
    assert settings.configured is True
    assert settings.client_id == "personal-client-id"
    assert settings.client_secret == "personal-client-secret"
    assert settings.refresh_token == "personal-refresh-token"
    assert settings.user_id == "me"
    assert settings.query == "label:inbox has:attachment"
    assert settings.allowed_senders == ("indeed@example.com", "jobs@example.net")
    assert not hasattr(settings, "password")


def test_gmail_settings_default_to_disabled_unconfigured(monkeypatch):
    for key in (
        "GMAIL_ENABLED",
        "GMAIL_CLIENT_ID",
        "GMAIL_CLIENT_SECRET",
        "GMAIL_REFRESH_TOKEN",
        "GMAIL_USER_ID",
        "GMAIL_QUERY",
        "GMAIL_ALLOWED_SENDERS",
    ):
        monkeypatch.delenv(key, raising=False)

    settings = config.get_gmail_settings()

    assert settings.enabled is False
    assert settings.configured is False
    assert settings.user_id == "me"
    assert settings.query == "has:attachment"
    assert settings.allowed_senders == ()


def test_odoo_settings_default_to_disabled_unconfigured(monkeypatch):
    for key in (
        "ODOO_ENABLED",
        "ODOO_BASE_URL",
        "ODOO_DATABASE",
        "ODOO_USERNAME",
        "ODOO_SECRET_ID",
        "ODOO_REQUEST_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(key, raising=False)

    settings = config.get_odoo_settings()

    assert settings.enabled is False
    assert settings.configured is False
    assert settings.base_url == ""
    assert settings.database == ""
    assert settings.username == ""
    assert settings.secret_id == "/ai-recruiter/prod/odoo"
    assert settings.request_timeout_seconds == 15.0


def test_odoo_settings_are_environment_driven_without_api_key(monkeypatch):
    monkeypatch.setenv("ODOO_ENABLED", "true")
    monkeypatch.setenv("ODOO_BASE_URL", "https://odoo.example.com/")
    monkeypatch.setenv("ODOO_DATABASE", "asiati")
    monkeypatch.setenv("ODOO_USERNAME", "integration@example.com")
    monkeypatch.setenv("ODOO_SECRET_ID", "/custom/odoo")
    monkeypatch.setenv("ODOO_REQUEST_TIMEOUT_SECONDS", "22")

    settings = config.get_odoo_settings()

    assert settings.enabled is True
    assert settings.configured is True
    assert settings.base_url == "https://odoo.example.com"
    assert settings.database == "asiati"
    assert settings.username == "integration@example.com"
    assert settings.secret_id == "/custom/odoo"
    assert settings.request_timeout_seconds == 22.0
    assert not hasattr(settings, "api_key")


def test_indeed_resume_agent_settings_defaults(monkeypatch):
    for key in (
        "INDEED_RESUME_AGENT_SECRET_ID",
        "INDEED_RESUME_AGENT_LEASE_SECONDS",
        "INDEED_RESUME_AGENT_MAX_ATTEMPTS",
        "INDEED_RESUME_AGENT_SENDER_DOMAINS",
        "INDEED_RESUME_AGENT_RESUME_HOST_SUFFIXES",
    ):
        monkeypatch.delenv(key, raising=False)

    settings = config.get_indeed_resume_agent_settings()

    assert settings.secret_id == "/ai-recruiter/prod/indeed-resume-agent"
    assert settings.lease_seconds == 600
    assert settings.max_attempts == 3
    assert settings.sender_domains == ("indeedemail.com",)
    assert settings.resume_host_suffixes == ("indeed.com", "indeedemail.com")


def test_indeed_resume_agent_settings_environment_overrides(monkeypatch):
    monkeypatch.setenv("INDEED_RESUME_AGENT_SECRET_ID", "/custom/agent")
    monkeypatch.setenv("INDEED_RESUME_AGENT_LEASE_SECONDS", "900")
    monkeypatch.setenv("INDEED_RESUME_AGENT_MAX_ATTEMPTS", "5")
    monkeypatch.setenv(
        "INDEED_RESUME_AGENT_SENDER_DOMAINS",
        " indeedemail.com , notify.indeed.test ",
    )
    monkeypatch.setenv(
        "INDEED_RESUME_AGENT_RESUME_HOST_SUFFIXES",
        "indeed.com,secure.indeed.test",
    )

    settings = config.get_indeed_resume_agent_settings()

    assert settings.secret_id == "/custom/agent"
    assert settings.lease_seconds == 900
    assert settings.max_attempts == 5
    assert settings.sender_domains == ("indeedemail.com", "notify.indeed.test")
    assert settings.resume_host_suffixes == ("indeed.com", "secure.indeed.test")
