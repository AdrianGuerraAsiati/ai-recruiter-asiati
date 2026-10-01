"""Odoo transport composition and secret-boundary tests."""

from app.config import OdooSettings
from app.domains.odoo_sync import integration


class FakeSecretStore:
    def __init__(self, payload=None, error=None):
        self.payload = dict(payload or {})
        self.error = error

    def read(self):
        if self.error:
            raise self.error
        return dict(self.payload)


class FakeProxy:
    def __init__(self, url, **_kwargs):
        self.url = url


def _settings(**overrides):
    values = {
        "enabled": True,
        "base_url": "https://odoo.example.com",
        "database": "asiati",
        "username": "integration@example.com",
        "secret_id": "/ai-recruiter/prod/odoo",
        "request_timeout_seconds": 19.0,
    }
    values.update(overrides)
    return OdooSettings(**values)


def test_build_client_requires_enabled_integration():
    try:
        integration.build_odoo_client(
            settings=_settings(enabled=False),
            secret_store=FakeSecretStore({"api_key": "secret"}),
        )
    except integration.OdooDisabled:
        pass
    else:
        raise AssertionError("disabled Odoo integration must not build a client")


def test_build_client_requires_non_secret_settings():
    try:
        integration.build_odoo_client(
            settings=_settings(base_url=""),
            secret_store=FakeSecretStore({"api_key": "secret"}),
        )
    except integration.OdooNotConfigured:
        pass
    else:
        raise AssertionError("incomplete settings must not build a client")


def test_build_client_requires_api_key_in_secret_store():
    try:
        integration.build_odoo_client(
            settings=_settings(),
            secret_store=FakeSecretStore({}),
        )
    except integration.OdooNotConfigured:
        pass
    else:
        raise AssertionError("missing API key must not build a client")


def test_build_client_combines_non_secret_settings_with_runtime_key():
    client = integration.build_odoo_client(
        settings=_settings(),
        secret_store=FakeSecretStore({"api_key": "runtime-secret"}),
        proxy_factory=FakeProxy,
    )

    assert client.base_url == "https://odoo.example.com"
    assert client.database == "asiati"
    assert client.username == "integration@example.com"
    assert client.request_timeout_seconds == 19.0
    assert "runtime-secret" not in repr(client)


def test_connection_status_never_returns_api_key():
    status = integration.connection_status(
        settings=_settings(),
        secret_store=FakeSecretStore({"api_key": "runtime-secret"}),
    )

    assert status == {
        "enabled": True,
        "configured": True,
        "base_url": "https://odoo.example.com",
        "database_configured": True,
        "username_configured": True,
        "secret_id": "/ai-recruiter/prod/odoo",
    }
    assert "runtime-secret" not in repr(status)


def test_connection_status_degrades_to_unconfigured_when_secret_store_fails():
    status = integration.connection_status(
        settings=_settings(),
        secret_store=FakeSecretStore(error=RuntimeError("unavailable")),
    )

    assert status["enabled"] is True
    assert status["configured"] is False



def test_build_client_translates_secret_store_failure_to_not_configured():
    try:
        integration.build_odoo_client(
            settings=_settings(),
            secret_store=FakeSecretStore(error=RuntimeError("access denied")),
        )
    except integration.OdooNotConfigured as exc:
        assert str(exc) == "Odoo credential secret is unavailable."
    else:
        raise AssertionError("secret access failure must be translated safely")
