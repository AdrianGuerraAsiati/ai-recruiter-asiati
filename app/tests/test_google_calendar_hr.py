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
    def __init__(self, *, identity=google.DEFAULT_ACCOUNT_EMAIL, calendar_status=200):
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

    assert connected == {"connected": True, "connected_email": google.DEFAULT_ACCOUNT_EMAIL}
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
        "connected_email": google.DEFAULT_ACCOUNT_EMAIL,
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
        "connected_email": google.DEFAULT_ACCOUNT_EMAIL,
        "refresh_token": "calendar-private-token",
    }
    google.disconnect(store=store)
    assert store.data["refresh_token"] == "original-gmail-refresh"
    assert not google.status(store=store)["connected"]


def test_admin_can_replace_calendar_account_without_touching_gmail_grant(store):
    initial = google.status(store=store)
    assert initial["target_email"] == google.DEFAULT_ACCOUNT_EMAIL

    store.data["talent_calendar"] = {
        "target_email": google.DEFAULT_ACCOUNT_EMAIL,
        "connected_email": google.DEFAULT_ACCOUNT_EMAIL,
        "refresh_token": "old-calendar-grant",
    }
    status = google.set_target_email("seleccion@asiaticorp.com", store=store)
    assert status["target_email"] == "seleccion@asiaticorp.com"
    assert status["connected"] is False
    assert "refresh_token" not in store.data["talent_calendar"]
    assert store.data["refresh_token"] == "original-gmail-refresh"
    assert store.data["connected_email"] == "sistemas@asiati.com.co"
    assert store.data["talent_calendar"]["target_email"] == "seleccion@asiaticorp.com"


def test_account_change_requires_approved_corporate_domain(store):
    with pytest.raises(google.GoogleCalendarEmailError, match="DOMAIN_NOT_ALLOWED"):
        google.set_target_email("external@gmail.com", store=store)
    with pytest.raises(google.GoogleCalendarEmailError, match="EMAIL_INVALID"):
        google.set_target_email("invalid-input", store=store)
    assert google.status(store=store)["target_email"] == google.DEFAULT_ACCOUNT_EMAIL


def test_already_configured_account_change_is_noop(store):
    before = store.read()
    updated = google.set_target_email(google.DEFAULT_ACCOUNT_EMAIL, store=store)
    assert updated["target_email"] == google.DEFAULT_ACCOUNT_EMAIL
    assert store.read() == before


def test_pending_oauth_cannot_complete_after_account_change(store):
    from urllib.parse import parse_qs, urlsplit

    url = google.start_oauth(admin_sub="admin-1", store=store)["authorization_url"]
    state = parse_qs(urlsplit(url).query)["state"][0]
    google.set_target_email("seleccion@asiaticorp.com", store=store)
    with pytest.raises(
        google.GoogleCalendarAuthorizationError, match="TARGET_CHANGED"
    ):
        google.oauth_callback(code="code", state=state, store=store, http_client=FakeGoogleHttp())
    assert not google.status(store=store)["connected"]


def test_new_account_oauth_uses_new_identity_and_syncs_to_new_calendar(store, event):
    from urllib.parse import parse_qs, urlsplit

    target = "seleccion@asiaticorp.com"
    google.set_target_email(target, store=store)
    url = google.start_oauth(admin_sub="admin-2", store=store)["authorization_url"]
    assert "login_hint=seleccion%40asiaticorp.com" in url
    state = parse_qs(urlsplit(url).query)["state"][0]
    http = FakeGoogleHttp(identity=target)
    assert google.oauth_callback(
        code="code", state=state, store=store, http_client=http
    ) == {"connected": True, "connected_email": target}
    result = google.sync_event(event, store=store, http_client=http)
    assert result["synced"]
    assert "/seleccion%40asiaticorp.com/events" in http.posts[0][0]
    assert google.status(store=store)["connected"] is True


def test_google_account_change_refuses_wrong_identity(store):
    from urllib.parse import parse_qs, urlsplit

    google.set_target_email("seleccion@asiaticorp.com", store=store)
    url = google.start_oauth(admin_sub="admin-1", store=store)["authorization_url"]
    state = parse_qs(urlsplit(url).query)["state"][0]
    with pytest.raises(google.GoogleCalendarAuthorizationError, match="WRONG_ACCOUNT"):
        google.oauth_callback(
            code="code", state=state, store=store,
            http_client=FakeGoogleHttp(identity=google.DEFAULT_ACCOUNT_EMAIL),
        )
    assert google.status(store=store)["connected"] is False
