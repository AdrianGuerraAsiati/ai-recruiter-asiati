"""AWS Secrets Manager boundary for Odoo credentials."""

import json

import pytest
from botocore.exceptions import ClientError

from app.infrastructure.odoo_secret import OdooSecretStore


class FakeSecretsClient:
    def __init__(self, response=None, error=None):
        self.response = response or {}
        self.error = error
        self.calls = []

    def get_secret_value(self, *, SecretId):
        self.calls.append(SecretId)
        if self.error:
            raise self.error
        return dict(self.response)


def _client_error(code):
    return ClientError(
        {"Error": {"Code": code, "Message": code}},
        "GetSecretValue",
    )


def test_reads_api_key_document_from_configured_secret():
    client = FakeSecretsClient(
        {"SecretString": json.dumps({"api_key": "runtime-secret"})}
    )
    store = OdooSecretStore("/custom/odoo", client=client)

    assert store.read() == {"api_key": "runtime-secret"}
    assert client.calls == ["/custom/odoo"]


def test_missing_secret_returns_empty_document():
    store = OdooSecretStore(
        "/missing/odoo",
        client=FakeSecretsClient(error=_client_error("ResourceNotFoundException")),
    )

    assert store.read() == {}


def test_non_missing_aws_error_is_not_swallowed():
    store = OdooSecretStore(
        "/odoo",
        client=FakeSecretsClient(error=_client_error("AccessDeniedException")),
    )

    with pytest.raises(ClientError):
        store.read()


@pytest.mark.parametrize("raw", ["[]", "not-json"])
def test_invalid_secret_document_is_rejected(raw):
    store = OdooSecretStore(
        "/odoo",
        client=FakeSecretsClient({"SecretString": raw}),
    )

    with pytest.raises(RuntimeError, match="ODOO_SECRET_INVALID"):
        store.read()
