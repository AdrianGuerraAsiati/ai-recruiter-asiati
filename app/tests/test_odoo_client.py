"""Contracts for the Odoo XML-RPC transport."""

import xmlrpc.client

import pytest

from app.integrations.odoo.client import (
    OdooAuthenticationError,
    OdooRpcError,
    OdooUnsafeUrl,
    OdooXmlRpcClient,
)


class FakeCommon:
    def __init__(self, *, uid=7, fail_auth=False):
        self.uid = uid
        self.fail_auth = fail_auth
        self.authenticate_calls = []

    def version(self):
        return {
            "server_version": "18.0+e",
            "server_serie": "18.0",
            "protocol_version": 1,
        }

    def authenticate(self, database, username, api_key, context):
        self.authenticate_calls.append((database, username, api_key, context))
        if self.fail_auth:
            raise xmlrpc.client.Fault(1, "authentication failed")
        return self.uid


class FakeModels:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.calls = []

    def execute_kw(self, database, uid, api_key, model, method, args, kwargs):
        self.calls.append(
            (database, uid, api_key, model, method, args, kwargs)
        )
        if self.fail:
            raise xmlrpc.client.Fault(2, "secret remote details")
        if method == "fields_get":
            return {"name": {"type": "char", "required": True}}
        if method == "search_read":
            return [{"id": 3, "name": "Candidate"}]
        if method == "create":
            return 42
        if method == "write":
            return True
        return {"ok": True}


class ProxyFactory:
    def __init__(self, common=None, models=None):
        self.common = common or FakeCommon()
        self.models = models or FakeModels()
        self.urls = []

    def __call__(self, url, **_kwargs):
        self.urls.append(url)
        if url.endswith("/xmlrpc/2/common"):
            return self.common
        if url.endswith("/xmlrpc/2/object"):
            return self.models
        raise AssertionError(url)


def _client(factory=None, **overrides):
    values = {
        "base_url": "https://odoo.example.com/",
        "database": "asiati",
        "username": "integration@example.com",
        "api_key": "api-key",
        "proxy_factory": factory or ProxyFactory(),
    }
    values.update(overrides)
    return OdooXmlRpcClient(**values)


@pytest.mark.parametrize(
    "url",
    [
        "",
        "odoo.example.com",
        "http://odoo.example.com",
        "ftp://odoo.example.com",
        "https://user:pass@odoo.example.com",
        "https://odoo.example.com?token=secret",
        "https://odoo.example.com#fragment",
    ],
)
def test_rejects_unsafe_or_invalid_base_urls(url):
    with pytest.raises(OdooUnsafeUrl):
        _client(base_url=url)


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8069",
        "http://127.0.0.1:8069",
        "https://odoo.example.com",
    ],
)
def test_allows_https_and_local_http(url):
    client = _client(base_url=url)
    assert client.base_url == url.rstrip("/")


def test_requires_database_username_and_api_key():
    with pytest.raises(OdooAuthenticationError):
        _client(database="")
    with pytest.raises(OdooAuthenticationError):
        _client(username="")
    with pytest.raises(OdooAuthenticationError):
        _client(api_key="")


def test_uses_documented_common_and_object_endpoints():
    factory = ProxyFactory()

    _client(factory)

    assert factory.urls == [
        "https://odoo.example.com/xmlrpc/2/common",
        "https://odoo.example.com/xmlrpc/2/object",
    ]


def test_authentication_is_cached_without_exposing_key():
    factory = ProxyFactory()
    client = _client(factory)

    assert client.authenticate() == 7
    assert client.authenticate() == 7

    assert factory.common.authenticate_calls == [
        ("asiati", "integration@example.com", "api-key", {}),
    ]
    assert "api-key" not in repr(client)


def test_rejected_credentials_raise_sanitized_auth_error():
    factory = ProxyFactory(common=FakeCommon(uid=0))
    client = _client(factory)

    with pytest.raises(OdooAuthenticationError, match="rejected"):
        client.authenticate()


def test_authentication_transport_fault_is_sanitized():
    factory = ProxyFactory(common=FakeCommon(fail_auth=True))
    client = _client(factory)

    with pytest.raises(OdooRpcError, match="authentication request failed") as exc:
        client.authenticate()

    assert "secret remote details" not in str(exc.value)


def test_execute_kw_uses_authenticated_contract():
    factory = ProxyFactory()
    client = _client(factory)

    result = client.execute_kw(
        "hr.applicant",
        "search_read",
        [[["email_from", "=", "ana@example.com"]]],
        {"fields": ["id", "name"], "limit": 1},
    )

    assert result == [{"id": 3, "name": "Candidate"}]
    assert factory.models.calls == [
        (
            "asiati",
            7,
            "api-key",
            "hr.applicant",
            "search_read",
            [[["email_from", "=", "ana@example.com"]]],
            {"fields": ["id", "name"], "limit": 1},
        )
    ]


def test_rpc_fault_is_sanitized():
    factory = ProxyFactory(models=FakeModels(fail=True))
    client = _client(factory)

    with pytest.raises(OdooRpcError, match=r"hr\.applicant\.search_read") as exc:
        client.search_read("hr.applicant", [], fields=["id"], limit=1)

    assert "secret remote details" not in str(exc.value)


def test_convenience_methods_keep_business_mapping_outside_transport():
    factory = ProxyFactory()
    client = _client(factory)

    assert client.fields_get("hr.applicant")["name"]["type"] == "char"
    assert client.search_read("hr.applicant", [], fields=["id"], limit=1) == [
        {"id": 3, "name": "Candidate"}
    ]
    assert client.create("hr.applicant", {"name": "Ana"}) == 42
    assert client.write("hr.applicant", [42], {"name": "Ana Pérez"}) is True

    methods = [call[4] for call in factory.models.calls]
    assert methods == ["fields_get", "search_read", "create", "write"]


def test_healthcheck_returns_non_secret_metadata():
    client = _client()

    assert client.healthcheck() == {
        "connected": True,
        "uid": 7,
        "server_version": "18.0+e",
        "server_serie": "18.0",
        "protocol_version": 1,
    }
