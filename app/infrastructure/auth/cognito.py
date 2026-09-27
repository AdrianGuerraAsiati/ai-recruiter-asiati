"""AWS Cognito access-token validation infrastructure."""

from __future__ import annotations

import hashlib
import logging
import os
import time
from threading import Lock

import boto3
import requests
from jose import JWTError, jwt

from app.config import get_aws_region
from app.infrastructure.bedrock.session import get_cached_session

logger = logging.getLogger(__name__)


class CognitoAuthenticationError(Exception):
    """Raised when Cognito cannot validate an access token."""


_cognito_client = None
_jwks_cache: dict[str, dict] = {}
_jwks_cache_expires_at = 0.0
_jwks_lock = Lock()
_identity_cache: dict[str, tuple[float, dict[str, str | None]]] = {}
_identity_lock = Lock()


def get_cognito_client():
    """Return the cached Cognito IDP client."""
    global _cognito_client
    if _cognito_client is None:
        _cognito_client = boto3.client(
            "cognito-idp",
            region_name=get_aws_region(),
        )
    return _cognito_client


def _settings() -> tuple[str, str, str] | None:
    user_pool_id = os.getenv("COGNITO_USER_POOL_ID", "").strip()
    client_id = os.getenv("COGNITO_CLIENT_ID", "").strip()
    if not user_pool_id or not client_id:
        return None
    region = get_aws_region()
    issuer = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}"
    return user_pool_id, client_id, issuer


def _jwks_url(user_pool_id: str) -> str:
    region = get_aws_region()
    return (
        f"https://cognito-idp.{region}.amazonaws.com/"
        f"{user_pool_id}/.well-known/jwks.json"
    )


def _load_jwks(user_pool_id: str, *, force_refresh: bool = False) -> dict[str, dict]:
    global _jwks_cache, _jwks_cache_expires_at

    now = time.monotonic()
    if not force_refresh and _jwks_cache and now < _jwks_cache_expires_at:
        return _jwks_cache

    with _jwks_lock:
        now = time.monotonic()
        if not force_refresh and _jwks_cache and now < _jwks_cache_expires_at:
            return _jwks_cache

        response = requests.get(_jwks_url(user_pool_id), timeout=5)
        response.raise_for_status()
        payload = response.json()
        keys = {
            str(item.get("kid")): item
            for item in payload.get("keys", [])
            if item.get("kid")
        }
        if not keys:
            raise CognitoAuthenticationError()

        _jwks_cache = keys
        _jwks_cache_expires_at = now + 3600
        return _jwks_cache


def _decode_access_token(token: str) -> dict:
    settings = _settings()
    if settings is None:
        raise CognitoAuthenticationError()

    user_pool_id, client_id, issuer = settings

    try:
        header = jwt.get_unverified_header(token)
        kid = str(header.get("kid") or "")
        if not kid:
            raise CognitoAuthenticationError()

        keys = _load_jwks(user_pool_id)
        key = keys.get(kid)
        if key is None:
            keys = _load_jwks(user_pool_id, force_refresh=True)
            key = keys.get(kid)
        if key is None:
            raise CognitoAuthenticationError()

        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            issuer=issuer,
            options={"verify_aud": False},
        )
    except (JWTError, requests.RequestException, ValueError, TypeError) as exc:
        raise CognitoAuthenticationError() from exc

    if claims.get("token_use") != "access":
        raise CognitoAuthenticationError()
    if claims.get("client_id") != client_id:
        raise CognitoAuthenticationError()
    if not str(claims.get("sub") or "").strip():
        raise CognitoAuthenticationError()

    return claims


def _cache_key(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _cached_identity(token: str) -> dict[str, str | None] | None:
    key = _cache_key(token)
    now = time.monotonic()
    with _identity_lock:
        cached = _identity_cache.get(key)
        if cached is None:
            return None
        expires_at, identity = cached
        if now >= expires_at:
            _identity_cache.pop(key, None)
            return None
        return dict(identity)


def _token_cache_ttl(token: str, max_ttl_seconds: int) -> int:
    try:
        claims = jwt.get_unverified_claims(token)
        expires_at = int(claims.get("exp") or 0)
    except (JWTError, TypeError, ValueError):
        expires_at = 0

    if expires_at:
        remaining = max(0, expires_at - int(time.time()))
        return max(1, min(max_ttl_seconds, remaining))
    return max(1, min(max_ttl_seconds, 60))


def _remember_identity(
    token: str,
    identity: dict[str, str | None],
    *,
    ttl_seconds: int = 300,
) -> None:
    key = _cache_key(token)
    effective_ttl = _token_cache_ttl(token, ttl_seconds)
    with _identity_lock:
        _identity_cache[key] = (
            time.monotonic() + effective_ttl,
            dict(identity),
        )
        if len(_identity_cache) > 512:
            oldest_key = next(iter(_identity_cache))
            _identity_cache.pop(oldest_key, None)


def _provider_identity(token: str) -> dict[str, str | None]:
    response = get_cognito_client().get_user(AccessToken=token)
    attrs = {
        attribute["Name"]: attribute["Value"]
        for attribute in response.get("UserAttributes", [])
    }
    return {
        "sub": attrs.get("sub") or response.get("Username"),
        "email": attrs.get("email"),
    }


def validate_access_token(token: str) -> dict[str, str | None]:
    """Validate a Cognito access token and normalize the user identity.

    Production prefers local JWT verification using the Cognito JWKS. Access
    tokens do not always contain the email claim, so a short-lived provider
    lookup cache fills that attribute without paying the network cost on every
    authenticated request.

    When pool/client settings are absent, the previous Cognito get_user
    behavior remains the compatibility path.
    """

    cached = _cached_identity(token)
    if cached is not None:
        return cached

    settings = _settings()
    if settings is None:
        try:
            identity = _provider_identity(token)
            _remember_identity(token, identity)
            return identity
        except Exception as exc:
            logger.warning("Auth validation failed: %s", type(exc).__name__)
            raise CognitoAuthenticationError() from exc

    try:
        claims = _decode_access_token(token)
    except CognitoAuthenticationError as local_error:
        try:
            identity = _provider_identity(token)
            _remember_identity(token, identity, ttl_seconds=60)
            logger.warning("Local JWT validation unavailable; used Cognito fallback.")
            return identity
        except Exception as provider_error:
            logger.warning(
                "Auth validation failed locally (%s) and remotely (%s)",
                type(local_error.__cause__ or local_error).__name__,
                type(provider_error).__name__,
            )
            raise CognitoAuthenticationError() from provider_error

    identity = {
        "sub": str(claims.get("sub") or "").strip() or None,
        "email": str(claims.get("email") or "").strip().casefold() or None,
    }

    if identity["email"]:
        _remember_identity(token, identity)
        return identity

    try:
        provider_identity = _provider_identity(token)
    except Exception as exc:
        logger.warning("Cognito email lookup failed: %s", type(exc).__name__)
        raise CognitoAuthenticationError() from exc

    if provider_identity.get("sub") != identity["sub"]:
        logger.warning("Cognito identity mismatch after local JWT validation.")
        raise CognitoAuthenticationError()

    _remember_identity(token, provider_identity)
    return provider_identity


def get_admin_cognito_client():
    """Return a signed Cognito admin client using the runtime AWS session."""
    return get_cached_session().client(
        "cognito-idp",
        region_name=get_aws_region(),
    )
