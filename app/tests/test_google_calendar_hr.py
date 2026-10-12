"""HR-only Google Calendar OAuth and idempotent event synchronization."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.domains.recruitment_calendar import google
from app.models import Candidate, Job, RecruitmentEvent


class MemorySecretStore:
    def __init__(self, data):
        self.data = dict(data)

    def read(self):
        return dict(self.data)

    def write(self, data):
        self.data = dict(data)


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.payload = payload

    def json(self):
        return self.payload


class FakeGoogleHttp:
    def __init__(self, *, identity=google.HR_EMAIL, calendar_status=200):
        self.identity = identity
        self.calendar_status = calendar_status
        self.events = {}
        self.posts = []
        self.puts = []

    def post(self, url, *, data=None, headers=None, params=None, json=None):
        if url == google.GOOGLE_TOKEN_URL:
            if data["grant_type"] == "authorization_code":
                return FakeResponse(200, {
                    "access_token": "test-access",
                    "refresh_token": "test-calendar-refresh",
                })
            return FakeResponse(200, {"access_token": "test-access"})
        self.posts.append((url, params, json))
        event_id = json["id"]
        if event_id in self.events:
            return FakeResponse(409, {})
        self.events[event_id] = json
        return FakeResponse(201, {"htmlLink": "https://calendar.google.com/calendar/event?eid=fake"})

    def get(self, url, *, headers=None, params=None):
        if url == google.GOOGLE_USERINFO_URL:
            return FakeResponse(200, {"email": self.identity})
        return FakeResponse(self.calendar_status, {"items": []})

    def put(self, url, *, headers=None, params=None, json=None):
        self.puts.append((url, params, json))
        self.events[json["id"]] = json
        return FakeResponse(200, {"htmlLink": "https://calendar.google.com/calendar/event?eid=fake"})


@pytest.fixture()
def store():
    return MemorySecretStore({
        "client_id": "test-google-client",
        "client_secret": "test-google-secret",
        "state_secret": "test-signing-secret",
        "refresh_token": "original-gmail-refresh",
        "connected_email": "sistemas@asiati.com.co",
    })


@pytest.fixture()
def event():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    job = Job(title="Coordinador de operaciones", owner_sub="admin")
    candidate = Candidate(name="Ana Prueba", email="ana@example.com", owner_sub="admin")
    db.add_all([job, candidate])
    db.flush()
    start = datetime(2026, 10, 16, 14, tzinfo=timezone.utc)
    meeting = RecruitmentEvent(
        job_id=job.id,
        candidate_id=candidate.id,
        kind="ONSITE_INTERVIEW",
        starts_at=start,
        ends_at=start + timedelta(hours=1),
        created_by_sub="admin",
        status="SCHEDULED",
    )
    db.add(meeting)
    db.commit()
    db.refresh(meeting)
    yield meeting
    db.close()
    engine.dispose()


def test_not_connected_cannot_assume_systems_gmail_authorization(store):
    status = google.status(store=store)
    assert status["target_email"] == "talentohumano@asiati.com.co"
    assert status["connected"] is False
    assert "refresh_token" not in status
    assert "client_secret" not in status


def test_google_oauth_url_is_bound_to_hr_account_with_one_time_state(store):
    params = google.start_oauth(admin_sub="admin-1", store=store)
    assert "login_hint=talentohumano%40asiati.com.co" in params["authorization_url"]
    assert "gmail.readonly" not in params["authorization_url"]
    assert store.data["talent_calendar"]["pending_state_hash"]
    assert store.data["refresh_token"] == "original-gmail-refresh"


def test_google_callback_rejects_wrong_identity_and_preserves_gmail(store):
    from urllib.parse import parse_qs, urlsplit

    url = google.start_oauth(admin_sub="admin-1", store=store)["authorization_url"]
    state = parse_qs(urlsplit(url).query)["state"][0]
    http = FakeGoogleHttp(identity="sistemas@asiati.com.co")
    with pytest.raises(google.GoogleCalendarAuthorizationError, match="WRONG_ACCOUNT"):
        google.oauth_callback(code="code", state=state, store=store, http_client=http)
    assert google.status(store=store)["connected"] is False
    assert store.data["refresh_token"] == "original-gmail-refresh"


def test_callback_accepts_hr_account_only_and_preserves_independent_grants(store):
    from urllib.parse import parse_qs, urlsplit

    url = google.start_oauth(admin_sub="admin-1", store=store)["authorization_url"]
    state = parse_qs(urlsplit(url).query)["state"][0]
    http = FakeGoogleHttp()
    connected = google.oauth_callback(code="code", state=state, store=store, http_client=http)

    assert connected == {"connected": True, "connected_email": google.HR_EMAIL}
    assert google.status(store=store)["connected"] is True
    assert store.data["refresh_token"] == "original-gmail-refresh"
    assert store.data["connected_email"] == "sistemas@asiati.com.co"
    assert store.data["talent_calendar"]["refresh_token"] == "test-calendar-refresh"
    assert "pending_state_hash" not in store.data["talent_calendar"]
    with pytest.raises(google.GoogleCalendarAuthorizationError, match="STATE_USED"):
        google.oauth_callback(code="code", state=state, store=store, http_client=http)


def test_invalid_calendar_permission_never_persists_grant(store):
    from urllib.parse import parse_qs, urlsplit

    url = google.start_oauth(admin_sub="admin-1", store=store)["authorization_url"]
    state = parse_qs(urlsplit(url).query)["state"][0]
    with pytest.raises(google.GoogleCalendarRemoteError, match="ACCESS_DENIED"):
        google.oauth_callback(
            code="code", state=state, store=store,
            http_client=FakeGoogleHttp(calendar_status=403),
        )
    assert not google.status(store=store)["connected"]


def test_idempotent_event_sync_reuses_google_id_and_updates_in_place(store, event):
    store.data["talent_calendar"] = {
        "connected_email": google.HR_EMAIL,
        "refresh_token": "test-calendar-refresh",
    }
    http = FakeGoogleHttp()
    first = google.sync_event(event, store=store, http_client=http)
    assert first["synced"] is True
    assert len(http.events) == 1
    assert len(http.posts) == 1
    assert len(http.puts) == 0
    remote = next(iter(http.events.values()))
    assert remote["summary"] == "Entrevista presencial · Ana Prueba"
    assert remote["transparency"] == "opaque"
    assert remote["start"]["dateTime"].endswith("Z")
    assert "attendees" not in remote

    event.status = "CANCELED"
    second = google.sync_event(event, store=store, http_client=http)
    assert first["google_event_id"] == second["google_event_id"]
    assert len(http.events) == 1
    assert len(http.puts) == 1
    remote = next(iter(http.events.values()))
    assert remote["summary"].startswith("[Cancelada]")
    assert remote["transparency"] == "transparent"


def test_disconnect_only_clears_calendar_oauth(store):
    store.data["talent_calendar"] = {
        "connected_email": google.HR_EMAIL,
        "refresh_token": "calendar-private-token",
    }
    google.disconnect(store=store)
    assert store.data["refresh_token"] == "original-gmail-refresh"
    assert not google.status(store=store)["connected"]
