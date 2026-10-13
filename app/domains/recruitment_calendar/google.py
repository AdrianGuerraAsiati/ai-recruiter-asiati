"""Google Calendar OAuth and one-way recruitment-event synchronization.

The company Gmail OAuth secret is reused as a *container*, not as an identity:
the Calendar refresh token is stored in a separate nested namespace and must
belong to the exact HR account. Never fall back to the Systems account.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote, urlencode

import httpx
from sqlalchemy.orm import Session

from app.infrastructure.gmail_oauth_store import GmailOAuthSecretStore
from app.models import RecruitmentEvent

logger = logging.getLogger(__name__)

DEFAULT_ACCOUNT_EMAIL = "talentohumano@asiati.com.co"
# The configured account is persisted in Secrets Manager, never in code.
DEFAULT_ALLOWED_DOMAINS = ("asiati.com.co", "asiaticorp.com")
GOOGLE_SCOPE = (
    "https://www.googleapis.com/auth/calendar.events "
    "https://www.googleapis.com/auth/userinfo.email"
)
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
GOOGLE_EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars"
SECRET_KEY = "talent_calendar"
REDIRECT_URI = "https://talent.asiaticorp.com/api/recruitment-calendar/google/callback"
FRONTEND_RETURN_URL = "https://talent.asiaticorp.com/calendar"
MAX_STATE_AGE_SECONDS = 600


class GoogleCalendarConfigurationError(RuntimeError):
    pass


class GoogleCalendarAuthorizationError(RuntimeError):
    pass


class GoogleCalendarRemoteError(RuntimeError):
    pass


class GoogleCalendarEmailError(ValueError):
    pass


def _store(store=None):
    return store if store is not None else GmailOAuthSecretStore()


def _config(secret: dict) -> bool:
    return all(str(secret.get(key) or "").strip() for key in (
        "client_id", "client_secret", "state_secret"
    ))


def _calendar_secret(secret: dict) -> dict:
    data = secret.get(SECRET_KEY)
    return dict(data) if isinstance(data, dict) else {}


def _target_email(calendar: dict) -> str:
    return str(calendar.get("target_email") or DEFAULT_ACCOUNT_EMAIL).strip().casefold()


def _allowed_domains() -> set[str]:
    """Admins may switch within approved company domains, configurable by ops."""
    configured = os.getenv("TALENT_GOOGLE_ALLOWED_DOMAINS")
    values = configured.split(",") if configured is not None else DEFAULT_ALLOWED_DOMAINS
    return {value.strip().casefold() for value in values if value.strip()}


def set_target_email(email: str, *, store=None) -> dict:
    """Switch the corporate account and invalidate any prior Calendar grant.

    A saved Google refresh token is always bound to the exact target email.
    Switching requires a fresh Google OAuth consent before syncing.
    """
    candidate = str(email or "").strip().casefold()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._%+\-]{0,63}@[a-z0-9.-]+", candidate):
        raise GoogleCalendarEmailError("GOOGLE_CALENDAR_EMAIL_INVALID")
    domain = candidate.rsplit("@", 1)[1]
    if domain not in _allowed_domains():
        raise GoogleCalendarEmailError("GOOGLE_CALENDAR_DOMAIN_NOT_ALLOWED")

    secret_store = _store(store)
    payload = dict(secret_store.read())
    calendar = _calendar_secret(payload)
    if candidate != _target_email(calendar):
        for key in (
            "refresh_token", "connected_email", "connected_at",
            "connected_by_sub", "pending_state_hash", "pending_at",
        ):
            calendar.pop(key, None)
        calendar["target_email"] = candidate
        payload[SECRET_KEY] = calendar
        secret_store.write(payload)
    return status(store=secret_store)


def _redirect_uri() -> str:
    return os.getenv("TALENT_GOOGLE_CALENDAR_REDIRECT_URI", REDIRECT_URI).strip()


def _return_url() -> str:
    return FRONTEND_RETURN_URL


def status(*, store=None) -> dict:
    """Show safe HR connection metadata; never reveal tokens or secrets."""
    try:
        payload = _store(store).read()
    except Exception:
        payload = {}
    calendar = _calendar_secret(payload)
    connected_email = str(calendar.get("connected_email") or "").strip().casefold()
    target_email = _target_email(calendar)
    return {
        "target_email": target_email,
        "connected": bool(
            _config(payload)
            and calendar.get("refresh_token")
            and connected_email == target_email
        ),
        "connected_email": connected_email or None,
        "oauth_configured": _config(payload) and bool(_redirect_uri()),
        "redirect_uri": _redirect_uri(),
        "direction": "TALENT_TO_GOOGLE",
    }


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _sign_state(payload: dict, key: str) -> str:
    body = _b64(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
    signature = hmac.new(key.encode(), body.encode("ascii"), hashlib.sha256).digest()
    return body + "." + _b64(signature)


def _check_state(value: str, key: str) -> dict:
    try:
        encoded, encoded_signature = value.split(".", 1)
        signature = _unb64(encoded_signature)
        expected = hmac.new(key.encode(), encoded.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("signature")
        payload = json.loads(_unb64(encoded))
        issued = int(payload.get("iat", 0))
        now = int(time.time())
        if payload.get("purpose") != "hr_calendar" or not (issued <= now + 30 and now - issued <= MAX_STATE_AGE_SECONDS):
            raise ValueError("expired")
        if not payload.get("sub") or not payload.get("nonce"):
            raise ValueError("missing")
        return payload
    except Exception as exc:
        raise GoogleCalendarAuthorizationError("GOOGLE_CALENDAR_OAUTH_STATE_INVALID") from exc


def start_oauth(*, admin_sub: str, store=None) -> dict:
    """Generate an HR-account-specific OAuth URL and a single-use state."""
    secret_store = _store(store)
    secret = dict(secret_store.read())
    if not _config(secret) or not _redirect_uri():
        raise GoogleCalendarConfigurationError("GOOGLE_CALENDAR_OAUTH_NOT_CONFIGURED")
    calendar = _calendar_secret(secret)
    target_email = _target_email(calendar)
    signed_state = _sign_state(
        {
            "email": target_email,
            "iat": int(time.time()),
            "sub": admin_sub,
            "nonce": secrets.token_urlsafe(24),
            "purpose": "hr_calendar",
        },
        str(secret["state_secret"]),
    )
    calendar["pending_state_hash"] = hashlib.sha256(signed_state.encode()).hexdigest()
    calendar["pending_at"] = int(time.time())
    secret[SECRET_KEY] = calendar
    secret_store.write(secret)

    query = urlencode({
        "client_id": str(secret["client_id"]),
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
        "scope": GOOGLE_SCOPE,
        "access_type": "offline",
        "prompt": "consent select_account",
        "login_hint": target_email,
        "state": signed_state,
    })
    return {"authorization_url": GOOGLE_AUTH_URL + "?" + query, "target_email": target_email}


def oauth_callback(*, code: str, state: str, store=None, http_client=None) -> dict:
    """Validate the Google identity and store only the HR OAuth grant."""
    secret_store = _store(store)
    secret = dict(secret_store.read())
    if not _config(secret):
        raise GoogleCalendarConfigurationError("GOOGLE_CALENDAR_OAUTH_NOT_CONFIGURED")
    state_data = _check_state(state, str(secret["state_secret"]))
    calendar = _calendar_secret(secret)
    target_email = _target_email(calendar)
    if state_data.get("email") != target_email:
        raise GoogleCalendarAuthorizationError("GOOGLE_CALENDAR_TARGET_CHANGED")
    if not hmac.compare_digest(
        str(calendar.get("pending_state_hash") or ""),
        hashlib.sha256(state.encode()).hexdigest(),
    ):
        raise GoogleCalendarAuthorizationError("GOOGLE_CALENDAR_OAUTH_STATE_USED")

    owns_client = http_client is None
    http = http_client or httpx.Client(timeout=12)
    try:
        token_response = http.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": str(secret["client_id"]),
                "client_secret": str(secret["client_secret"]),
                "redirect_uri": _redirect_uri(),
                "grant_type": "authorization_code",
            },
        )
        if token_response.status_code != 200:
            raise GoogleCalendarRemoteError("GOOGLE_CALENDAR_OAUTH_EXCHANGE_FAILED")
        token_payload = token_response.json()
        access_token = str(token_payload.get("access_token") or "")
        refresh_token = str(token_payload.get("refresh_token") or "")
        if not access_token or not refresh_token:
            raise GoogleCalendarRemoteError("GOOGLE_CALENDAR_REFRESH_TOKEN_MISSING")

        profile_response = http.get(
            GOOGLE_USERINFO_URL, headers={"Authorization": "Bearer " + access_token}
        )
        if profile_response.status_code != 200:
            raise GoogleCalendarRemoteError("GOOGLE_CALENDAR_IDENTITY_CHECK_FAILED")
        connected_email = str(profile_response.json().get("email") or "").casefold()
        if connected_email != target_email:
            raise GoogleCalendarAuthorizationError("GOOGLE_CALENDAR_WRONG_ACCOUNT")

        # A successful OAuth grant without Calendar API permissions is not a connection.
        calendar_response = http.get(
            GOOGLE_EVENTS_URL + "/" + quote(target_email, safe="") + "/events",
            headers={"Authorization": "Bearer " + access_token},
            params={"maxResults": 1},
        )
        if calendar_response.status_code != 200:
            raise GoogleCalendarRemoteError("GOOGLE_CALENDAR_ACCESS_DENIED")
    except (httpx.RequestError, ValueError) as exc:
        raise GoogleCalendarRemoteError("GOOGLE_CALENDAR_OAUTH_NETWORK_ERROR") from exc
    finally:
        if owns_client:
            http.close()

    calendar.update({
        "refresh_token": refresh_token,
        "connected_email": connected_email,
        "connected_by_sub": state_data["sub"],
        "connected_at": datetime.now(timezone.utc).isoformat(),
    })
    calendar.pop("pending_state_hash", None)
    calendar.pop("pending_at", None)
    secret[SECRET_KEY] = calendar
    secret_store.write(secret)
    return {"connected": True, "connected_email": target_email}


def disconnect(*, store=None) -> dict:
    """Revoke the local connection without modifying the Gmail grant."""
    secret_store = _store(store)
    secret = dict(secret_store.read())
    calendar = _calendar_secret(secret)
    calendar.pop("refresh_token", None)
    calendar.pop("connected_email", None)
    calendar.pop("pending_state_hash", None)
    calendar.pop("pending_at", None)
    secret[SECRET_KEY] = calendar
    secret_store.write(secret)
    return {"connected": False, "target_email": _target_email(calendar)}


def _access_token(secret: dict, http) -> str:
    calendar = _calendar_secret(secret)
    if not _config(secret) or str(calendar.get("connected_email") or "").casefold() != _target_email(calendar) or not calendar.get("refresh_token"):
        raise GoogleCalendarConfigurationError("GOOGLE_CALENDAR_NOT_CONNECTED")
    response = http.post(
        GOOGLE_TOKEN_URL,
        data={
            "client_id": str(secret["client_id"]),
            "client_secret": str(secret["client_secret"]),
            "refresh_token": str(calendar["refresh_token"]),
            "grant_type": "refresh_token",
        },
    )
    if response.status_code != 200:
        raise GoogleCalendarRemoteError("GOOGLE_CALENDAR_REFRESH_FAILED")
    token = str(response.json().get("access_token") or "")
    if not token:
        raise GoogleCalendarRemoteError("GOOGLE_CALENDAR_ACCESS_TOKEN_MISSING")
    return token


def _google_event_id(event: RecruitmentEvent) -> str:
    # Google event IDs accept the base32hex alphabet 0-9, a-v.
    # UUID hex is a subset, so this stable ID avoids a database migration.
    return "talent" + str(event.id).replace("-", "").lower()


def _utc_iso(date: datetime) -> str:
    if date.tzinfo is None:
        date = date.replace(tzinfo=timezone.utc)
    return date.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _event_body(event: RecruitmentEvent) -> dict:
    kind = "Videollamada" if event.kind == "PHONE_CALL" else "Visita presencial"
    cancelled = event.status == "CANCELED"
    prefix = "[Cancelada] " if cancelled else ""
    description = (
        f"Vacante: {event.job.title}\n"
        f"Candidato: {event.candidate.name}\n"
        f"Referencia Talent: {event.id}\n"
    )
    if event.notes:
        description += "Notas: " + str(event.notes) + "\n"
    body = {
        "id": _google_event_id(event),
        "summary": prefix + kind + " · " + event.candidate.name,
        "description": description,
        "start": {"dateTime": _utc_iso(event.starts_at)},
        "end": {"dateTime": _utc_iso(event.ends_at)},
        "location": "ASIATI" if event.kind == "ONSITE_INTERVIEW" else "",
        "transparency": "transparent" if cancelled else "opaque",
        "extendedProperties": {
            "private": {"talent_event_id": str(event.id), "origin": "talent_asiati"}
        },
    }
    if event.kind == "PHONE_CALL":
        body["conferenceData"] = {
            "createRequest": {
                "requestId": "talent-" + str(event.id).replace("-", "").lower(),
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        }
    return body


def _existing_conference(http, base_url: str, event_id: str, headers: dict) -> dict | None:
    """Preserve the existing Meet link when updating an event."""
    try:
        response = http.get(base_url + "/" + quote(event_id, safe=""), headers=headers,
                            params={"conferenceDataVersion": 1})
        if response.status_code == 200:
            return response.json().get("conferenceData")
    except httpx.RequestError:
        pass
    return None


def sync_event(event: RecruitmentEvent, *, store=None, http_client=None) -> dict:
    """Idempotent upsert into HR's calendar, including canceled appointments.

    Canceled events are shown as canceled and marked free rather than deleted:
    reactivating a canceled event can then safely reuse the same Google ID.
    Existing Google events not created by Talent are not read or altered.
    """
    secret = _store(store).read()
    target_email = _target_email(_calendar_secret(secret))
    owns_client = http_client is None
    http = http_client or httpx.Client(timeout=12)
    try:
        token = _access_token(secret, http)
        headers = {"Authorization": "Bearer " + token}
        url = GOOGLE_EVENTS_URL + "/" + quote(target_email, safe="") + "/events"
        body = _event_body(event)
        # First attempt deterministic insert; a conflict means this Talent
        # appointment already exists in Google, so update its known ID.
        response = http.post(
            url, headers=headers, params={"sendUpdates": "none", "conferenceDataVersion": 1}, json=body
        )
        if response.status_code == 409:
            response = http.put(
                url + "/" + quote(body["id"], safe=""),
                headers=headers,
                params={"sendUpdates": "none", "conferenceDataVersion": 1},
                json={**body, **({"conferenceData": self_conference} if (self_conference := _existing_conference(http, url, body["id"], headers)) else {})},
            )
        if response.status_code not in (200, 201):
            raise GoogleCalendarRemoteError(
                "GOOGLE_CALENDAR_EVENT_SYNC_HTTP_" + str(response.status_code)
            )
        result = response.json()
        return {
            "synced": True,
            "google_event_id": body["id"],
            "google_event_url": result.get("htmlLink"),
            "meet_url": result.get("hangoutLink") or next((entry.get("uri") for entry in result.get("conferenceData", {}).get("entryPoints", []) if entry.get("entryPointType") == "video"), None),
        }
    except httpx.RequestError as exc:
        raise GoogleCalendarRemoteError("GOOGLE_CALENDAR_EVENT_SYNC_NETWORK_ERROR") from exc
    finally:
        if owns_client:
            http.close()


def try_sync_event(event: RecruitmentEvent) -> dict:
    """Never rollback a Talent appointment if Google's integration is offline."""
    if os.getenv("TALENT_GOOGLE_CALENDAR_AUTOSYNC", "true").casefold() not in {
        "true", "1", "yes", "on"
    }:
        return {"synced": False, "reason": "AUTOSYNC_DISABLED"}
    if not status()["connected"]:
        return {"synced": False, "reason": "NOT_CONNECTED"}
    try:
        return sync_event(event)
    except (GoogleCalendarRemoteError, GoogleCalendarConfigurationError) as exc:
        logger.warning("Recruitment Google Calendar synchronization failed: %s", exc)
        return {"synced": False, "reason": "GOOGLE_UNAVAILABLE"}


def sync_upcoming(db: Session, *, limit: int = 100, store=None, http_client=None) -> dict:
    """Retry recent/upcoming Talent events without touching unrelated Google events."""
    if not status(store=store)["connected"]:
        raise GoogleCalendarConfigurationError("GOOGLE_CALENDAR_NOT_CONNECTED")
    since = datetime.now(timezone.utc) - timedelta(days=7)
    events = (
        db.query(RecruitmentEvent)
        .filter(RecruitmentEvent.ends_at >= since)
        .order_by(RecruitmentEvent.starts_at.asc())
        .limit(min(max(1, limit), 100))
        .all()
    )
    synced = 0
    failed = 0
    for event in events:
        # Loaded ORM events have their candidate/job relationships.
        try:
            sync_event(event, store=store, http_client=http_client)
            synced += 1
        except (GoogleCalendarRemoteError, GoogleCalendarConfigurationError):
            failed += 1
    return {"total": len(events), "synced": synced, "failed": failed, "target_email": status(store=store)["target_email"]}
