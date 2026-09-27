import pytest
from fastapi import HTTPException, Request

import app.deps as deps
from app.infrastructure.auth import cognito


@pytest.fixture(autouse=True)
def _clear_cognito_caches(monkeypatch):
    cognito._identity_cache.clear()
    cognito._jwks_cache.clear()
    cognito._jwks_cache_expires_at = 0.0
    monkeypatch.delenv("COGNITO_USER_POOL_ID", raising=False)
    monkeypatch.delenv("COGNITO_CLIENT_ID", raising=False)


def _request(authorization: str | None = None) -> Request:
    headers = []
    if authorization is not None:
        headers.append((b"authorization", authorization.encode("utf-8")))
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers})


def test_missing_authorization_header_keeps_401_contract():
    with pytest.raises(HTTPException) as exc_info:
        deps.get_current_user(_request())
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "No token provided."


def test_validate_access_token_normalizes_sub_and_email(monkeypatch):
    class FakeCognito:
        def get_user(self, *, AccessToken):
            assert AccessToken == "token-123"
            return {
                "Username": "legacy-user",
                "UserAttributes": [
                    {"Name": "sub", "Value": "stable-sub"},
                    {"Name": "email", "Value": "person@example.com"},
                ],
            }

    monkeypatch.setattr(cognito, "get_cognito_client", lambda: FakeCognito())
    user = cognito.validate_access_token("token-123")
    assert user == {"sub": "stable-sub", "email": "person@example.com"}


def test_validate_access_token_preserves_username_fallback(monkeypatch):
    class FakeCognito:
        def get_user(self, *, AccessToken):
            return {
                "Username": "legacy-user",
                "UserAttributes": [{"Name": "email", "Value": "person@example.com"}],
            }

    monkeypatch.setattr(cognito, "get_cognito_client", lambda: FakeCognito())
    user = cognito.validate_access_token("token-123")
    assert user == {"sub": "legacy-user", "email": "person@example.com"}


def test_validate_access_token_wraps_provider_failure(monkeypatch):
    class FakeCognito:
        def get_user(self, *, AccessToken):
            raise RuntimeError("provider rejected token")

    monkeypatch.setattr(cognito, "get_cognito_client", lambda: FakeCognito())
    with pytest.raises(cognito.CognitoAuthenticationError):
        cognito.validate_access_token("bad-token")


def test_invalid_cognito_token_keeps_401_contract(monkeypatch):
    def _reject(_token):
        raise cognito.CognitoAuthenticationError()

    monkeypatch.setattr(deps.cognito, "validate_access_token", _reject)
    with pytest.raises(HTTPException) as exc_info:
        deps.get_current_user(_request("Bearer bad-token"))
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Token invalido o expirado."



def test_local_access_token_with_email_skips_provider_lookup(monkeypatch):
    monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-east-2_TestPool")
    monkeypatch.setenv("COGNITO_CLIENT_ID", "client-123")
    monkeypatch.setattr(
        cognito,
        "_decode_access_token",
        lambda token: {
            "sub": "stable-sub",
            "email": "Person@Example.COM",
            "token_use": "access",
            "client_id": "client-123",
        },
    )

    class UnexpectedProvider:
        def get_user(self, **kwargs):
            raise AssertionError("provider lookup should not run when email is in claims")

    monkeypatch.setattr(cognito, "get_cognito_client", lambda: UnexpectedProvider())

    user = cognito.validate_access_token("signed-token")
    assert user == {"sub": "stable-sub", "email": "person@example.com"}


def test_local_access_token_without_email_caches_provider_identity(monkeypatch):
    monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-east-2_TestPool")
    monkeypatch.setenv("COGNITO_CLIENT_ID", "client-123")
    monkeypatch.setattr(
        cognito,
        "_decode_access_token",
        lambda token: {
            "sub": "stable-sub",
            "token_use": "access",
            "client_id": "client-123",
        },
    )

    calls = []

    class FakeProvider:
        def get_user(self, *, AccessToken):
            calls.append(AccessToken)
            return {
                "Username": "legacy-user",
                "UserAttributes": [
                    {"Name": "sub", "Value": "stable-sub"},
                    {"Name": "email", "Value": "person@example.com"},
                ],
            }

    monkeypatch.setattr(cognito, "get_cognito_client", lambda: FakeProvider())

    first = cognito.validate_access_token("signed-token")
    second = cognito.validate_access_token("signed-token")

    assert first == {"sub": "stable-sub", "email": "person@example.com"}
    assert second == first
    assert calls == ["signed-token"]


def test_local_access_token_rejects_provider_subject_mismatch(monkeypatch):
    monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-east-2_TestPool")
    monkeypatch.setenv("COGNITO_CLIENT_ID", "client-123")
    monkeypatch.setattr(
        cognito,
        "_decode_access_token",
        lambda token: {
            "sub": "expected-sub",
            "token_use": "access",
            "client_id": "client-123",
        },
    )

    class WrongProvider:
        def get_user(self, *, AccessToken):
            return {
                "Username": "other-user",
                "UserAttributes": [
                    {"Name": "sub", "Value": "other-sub"},
                    {"Name": "email", "Value": "person@example.com"},
                ],
            }

    monkeypatch.setattr(cognito, "get_cognito_client", lambda: WrongProvider())

    with pytest.raises(cognito.CognitoAuthenticationError):
        cognito.validate_access_token("signed-token")


def test_local_validation_failure_uses_short_provider_fallback(monkeypatch):
    monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-east-2_TestPool")
    monkeypatch.setenv("COGNITO_CLIENT_ID", "client-123")

    def _reject(_token):
        raise cognito.CognitoAuthenticationError()

    monkeypatch.setattr(cognito, "_decode_access_token", _reject)

    class FakeProvider:
        def get_user(self, *, AccessToken):
            return {
                "Username": "legacy-user",
                "UserAttributes": [
                    {"Name": "sub", "Value": "stable-sub"},
                    {"Name": "email", "Value": "person@example.com"},
                ],
            }

    monkeypatch.setattr(cognito, "get_cognito_client", lambda: FakeProvider())

    assert cognito.validate_access_token("signed-token") == {
        "sub": "stable-sub",
        "email": "person@example.com",
    }



def test_local_decoder_rejects_wrong_token_use(monkeypatch):
    monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-east-2_TestPool")
    monkeypatch.setenv("COGNITO_CLIENT_ID", "client-123")
    monkeypatch.setattr(
        cognito.jwt,
        "get_unverified_header",
        lambda token: {"kid": "kid-1"},
    )
    monkeypatch.setattr(
        cognito,
        "_load_jwks",
        lambda pool_id, force_refresh=False: {"kid-1": {"kid": "kid-1"}},
    )
    monkeypatch.setattr(
        cognito.jwt,
        "decode",
        lambda *args, **kwargs: {
            "sub": "stable-sub",
            "token_use": "id",
            "client_id": "client-123",
        },
    )

    with pytest.raises(cognito.CognitoAuthenticationError):
        cognito._decode_access_token("token")


def test_local_decoder_rejects_wrong_client_id(monkeypatch):
    monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-east-2_TestPool")
    monkeypatch.setenv("COGNITO_CLIENT_ID", "expected-client")
    monkeypatch.setattr(
        cognito.jwt,
        "get_unverified_header",
        lambda token: {"kid": "kid-1"},
    )
    monkeypatch.setattr(
        cognito,
        "_load_jwks",
        lambda pool_id, force_refresh=False: {"kid-1": {"kid": "kid-1"}},
    )
    monkeypatch.setattr(
        cognito.jwt,
        "decode",
        lambda *args, **kwargs: {
            "sub": "stable-sub",
            "token_use": "access",
            "client_id": "other-client",
        },
    )

    with pytest.raises(cognito.CognitoAuthenticationError):
        cognito._decode_access_token("token")


def test_identity_cache_ttl_never_outlives_access_token(monkeypatch):
    monkeypatch.setattr(
        cognito.jwt,
        "get_unverified_claims",
        lambda token: {"exp": int(cognito.time.time()) + 15},
    )

    assert cognito._token_cache_ttl("token", 300) <= 15
