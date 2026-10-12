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

HR_EMAIL = "talentohumano@asiati.com.co"
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


def _store(store=None):
    return store if store is not None else GmailOAuthSecretStore()


def _config(secret: dict) -> bool:
    return all(str(secret.get(key) or "").strip() for key in (
        "client_id", "client_secret", "state_secret"
    ))


def _calendar_secret(secret: dict) -> dict:
    data = secret.get(SECRET_KEY)
    return dict(data) if isinstance(data, dict) else {}


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
    return {
        "target_email": HR_EMAIL,
        "connected": bool(
            _config(payload)
            and calendar.get("refresh_token")
            and connected_email == HR_EMAIL
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
    signed_state = _sign_state(
        {
            "iat": int(time.time()),
            "sub": admin_sub,
            "nonce": secrets.token_urlsafe(24),
            "purpose": "hr_calendar",
        },
        str(secret["state_secret"]),
    )
    calendar = _calendar_secret(secret)
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
        "login_hint": HR_EMAIL,
        "state": signed_state,
    })
    return {"authorization_url": GOOGLE_AUTH_URL + "?" + query, "target_email": HR_EMAIL}


def oauth_callback(*, code: str, state: str, store=None, http_client=None) -> dict:
    """Validate the Google identity and store only the HR OAuth grant."""
    secret_store = _store(store)
    secret = dict(secret_store.read())
    if not _config(secret):
        raise GoogleCalendarConfigurationError("GOOGLE_CALENDAR_OAUTH_NOT_CONFIGURED")
    state_data = _check_state(state, str(secret["state_secret"]))
    calendar = _calendar_secret(secret)
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
        if connected_email != HR_EMAIL:
            raise GoogleCalendarAuthorizationError("GOOGLE_CALENDAR_WRONG_ACCOUNT")

        # A successful OAuth grant without Calendar API permissions is not a connection.
        calendar_response = http.get(
            GOOGLE_EVENTS_URL + "/" + quote(HR_EMAIL, safe="") + "/events",
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
    return {"connected": True, "connected_email": HR_EMAIL}


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
    return {"connected": False, "target_email": HR_EMAIL}


def _access_token(secret: dict, http) -> str:
    calendar = _calendar_secret(secret)
    if not _config(secret) or str(calendar.get("connected_email") or "").casefold() != HR_EMAIL or not calendar.get("refresh_token"):
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
    kind = "Llamada" if event.kind == "PHONE_CALL" else "Entrevista presencial"
    cancelled = event.status == "CANCELED"
    prefix = "[Cancelada] " if cancelled else ""
    description = (
        f"Vacante: {event.job.title}\n"
        f"Candidato: {event.candidate.name}\n"
        f"Referencia Talent: {event.id}\n"
    )
    if event.notes:
        description += "Notas: " + str(event.notes) + "\n"
    return {
        "id": _google_event_id(event),
        "summary": prefix + kind + " · " + event.candidate.name,
        "description": description,
        "start": {"dateTime": _utc_iso(event.starts_at)},
        "end": {"dateTime": _utc_iso(event.ends_at)},
        "location": event.location or "",
        "transparency": "transparent" if cancelled else "opaque",
        "extendedProperties": {
            "private": {"talent_event_id": str(event.id), "origin": "talent_asiati"}
        },
    }


def sync_event(event: RecruitmentEvent, *, store=None, http_client=None) -> dict:
    """Idempotent upsert into HR's calendar, including canceled appointments.

    Canceled events are shown as canceled and marked free rather than deleted:
    reactivating a canceled event can then safely reuse the same Google ID.
    Existing Google events not created by Talent are not read or altered.
    """
    secret = _store(store).read()
    owns_client = http_client is None
    http = http_client or httpx.Client(timeout=12)
    try:
        token = _access_token(secret, http)
        headers = {"Authorization": "Bearer " + token}
        url = GOOGLE_EVENTS_URL + "/" + quote(HR_EMAIL, safe="") + "/events"
        body = _event_body(event)
        # First attempt deterministic insert; a conflict means this Talent
        # appointment already exists in Google, so update its known ID.
        response = http.post(
            url, headers=headers, params={"sendUpdates": "none"}, json=body
        )
        if response.status_code == 409:
            response = http.put(
                url + "/" + quote(body["id"], safe=""),
                headers=headers,
                params={"sendUpdates": "none"},
                json=body,
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
        }
    except httpx.RequestError as exc:
        raise GoogleCalendarRemoteError("GOOGLE_CALENDAR_EVENT_SYNC_NETWORK_ERROR") from exc
    finally:
        if owns_client:
            http.close()


def try_sync_event(event: RecruitmentEvent) -> dict:
    """Never rollback a Talent appointment if Google's integration is offline."""
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
    from app.domains.recruitment_calendar import repository

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
    return {"total": len(events), "synced": synced, "failed": failed, "target_email": HR_EMAIL}
