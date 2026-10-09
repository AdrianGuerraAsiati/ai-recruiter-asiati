import hashlib
from types import SimpleNamespace

import pytest

from app.domains.candidate_ingestion import agent_source_service


class FakeDB:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def refresh(self, value):
        return None


class FakeStorage:
    def __init__(self):
        self.calls = []

    def store_source_document(self, **kwargs):
        self.calls.append(kwargs)
        return "candidate-ingestion/event-1/source/resume.pdf"


def test_computrabajo_candidate_is_handed_to_shared_ingestion_queue(monkeypatch):
    db = FakeDB()
    storage = FakeStorage()
    created = {}
    queued = []

    event = SimpleNamespace(
        id="event-1",
        status="RECEIVED",
        job_id=None,
        last_error_code=None,
        last_error_message=None,
        queue_dispatched_at=None,
    )

    monkeypatch.setattr(
        agent_source_service.repository,
        "get_event_by_external_id",
        lambda *args, **kwargs: None,
    )

    def create_event(_db, **kwargs):
        created["event"] = kwargs
        return event

    monkeypatch.setattr(agent_source_service.repository, "create_event", create_event)
    monkeypatch.setattr(
        agent_source_service.repository,
        "create_document",
        lambda _db, **kwargs: created.setdefault("document", kwargs),
    )
    monkeypatch.setattr(
        agent_source_service.queue,
        "send_candidate_ingestion",
        lambda event_id: queued.append(event_id) or "message-1",
    )

    payload = b"%PDF-1.7\ncomputrabajo"

    result = agent_source_service.ingest_candidate_document(
        db,
        owner_sub="owner-1",
        provider="computrabajo",
        source_account="corporate-recruiting",
        external_id="ids:candidate-42",
        candidate_name="Ada Lovelace",
        job_title="Ingeniera de software",
        external_job_id="offer-7",
        location="Bogotá, D.C.",
        filename="ada.pdf",
        content_type="application/pdf",
        data=payload,
        storage=storage,
    )

    assert result.provider == "COMPUTRABAJO"
    assert result.event_id == "event-1"
    assert result.existing is False
    assert result.queued is True
    assert event.job_id is None
    assert event.status == "STORED"
    assert queued == ["event-1"]
    assert created["event"]["source"] == "AGENT"
    assert created["event"]["provider"] == "COMPUTRABAJO"
    assert created["event"]["raw_metadata"] == {
        "candidate_name": "Ada Lovelace",
        "source_provider": "COMPUTRABAJO",
        "location": "Bogotá, D.C.",
    }
    assert created["document"]["document_sha256"] == hashlib.sha256(payload).hexdigest()
    assert storage.calls[0]["content_type"] == "application/pdf"


def test_computrabajo_replay_with_same_document_is_idempotent(monkeypatch):
    db = FakeDB()
    payload = b"%PDF-1.7\nsame"
    digest = hashlib.sha256(payload).hexdigest()
    event = SimpleNamespace(
        id="event-1",
        status="COMPLETED",
        queue_dispatched_at=object(),
    )
    document = SimpleNamespace(document_sha256=digest)

    monkeypatch.setattr(
        agent_source_service.repository,
        "get_event_by_external_id",
        lambda *args, **kwargs: event,
    )
    monkeypatch.setattr(
        agent_source_service.repository,
        "list_documents",
        lambda *args, **kwargs: [document],
    )

    result = agent_source_service.ingest_candidate_document(
        db,
        owner_sub="owner-1",
        provider="COMPUTRABAJO",
        source_account="corporate-recruiting",
        external_id="ids:candidate-42",
        candidate_name="Ada Lovelace",
        job_title="Ingeniera de software",
        filename="ada.pdf",
        content_type="application/pdf",
        data=payload,
    )

    assert result.existing is True
    assert result.status == "COMPLETED"
    assert result.queued is True
    assert db.commits == 0


def test_candidate_source_rejects_unknown_provider_and_non_resume_bytes():
    db = FakeDB()

    with pytest.raises(
        agent_source_service.CandidateSourceValidationError,
        match="CANDIDATE_SOURCE_PROVIDER_UNSUPPORTED",
    ):
        agent_source_service.ingest_candidate_document(
            db,
            owner_sub="owner-1",
            provider="UNTRUSTED",
            source_account="account",
            external_id="1",
            candidate_name="Ada",
            job_title="Engineer",
            filename="cv.pdf",
            content_type="application/pdf",
            data=b"%PDF-1.7",
        )

    with pytest.raises(
        agent_source_service.CandidateSourceValidationError,
        match="CANDIDATE_SOURCE_DOCUMENT_UNSUPPORTED",
    ):
        agent_source_service.ingest_candidate_document(
            db,
            owner_sub="owner-1",
            provider="COMPUTRABAJO",
            source_account="account",
            external_id="1",
            candidate_name="Ada",
            job_title="Engineer",
            filename="cv.pdf",
            content_type="application/pdf",
            data=b"not-a-document",
        )


def test_computrabajo_does_not_require_a_job_title_or_create_a_job(monkeypatch):
    db = FakeDB()
    event = SimpleNamespace(id="candidate-only", status="RECEIVED", job_id=None,
                            last_error_code=None, last_error_message=None,
                            queue_dispatched_at=None)
    monkeypatch.setattr(agent_source_service.repository, "get_event_by_external_id", lambda *a, **kw: None)
    monkeypatch.setattr(agent_source_service.repository, "create_event", lambda *a, **kw: event)
    monkeypatch.setattr(agent_source_service.repository, "create_document", lambda *a, **kw: None)
    monkeypatch.setattr(agent_source_service.queue, "send_candidate_ingestion", lambda *a: None)
    result = agent_source_service.ingest_candidate_document(
        db, owner_sub="owner", provider="COMPUTRABAJO", source_account="asiati",
        external_id="candidate-1", candidate_name="Persona Ejemplo", job_title=None,
        external_job_id="external-job", filename="cv.pdf", content_type="application/pdf",
        data=b"%PDF-1.4\\ntest", storage=FakeStorage(),
    )
    assert result.queued is True
    assert event.job_id is None


def test_existing_unqueued_candidate_is_dispatched_on_retry(monkeypatch):
    db = FakeDB()
    payload = b"%PDF-1.7\nretry"
    event = SimpleNamespace(
        id="event-retry", status="STORED", queue_dispatched_at=None,
    )
    monkeypatch.setattr(agent_source_service.repository,
        "get_event_by_external_id", lambda *a, **kw: event)
    monkeypatch.setattr(agent_source_service.repository,
        "list_documents", lambda *a, **kw: [
            SimpleNamespace(document_sha256=hashlib.sha256(payload).hexdigest())
        ])
    queued = []
    monkeypatch.setattr(agent_source_service.queue,
        "send_candidate_ingestion", lambda id: queued.append(id))
    result = agent_source_service.ingest_candidate_document(
        db, owner_sub="owner", provider="COMPUTRABAJO", source_account="asiati",
        external_id="candidate-1", candidate_name="Persona Ejemplo", job_title=None,
        filename="cv.pdf", content_type="application/pdf", data=payload,
    )
    assert result.existing is True and result.queued is True
    assert queued == ["event-retry"]
    assert db.commits == 1
