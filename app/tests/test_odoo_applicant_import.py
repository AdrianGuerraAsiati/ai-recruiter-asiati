"""Incremental Odoo applicant import tests."""

import base64

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.domains.candidate_ingestion.models import (
    CandidateIngestionCursor,
    CandidateIngestionDocument,
    CandidateIngestionEvent,
)
from app.domains.odoo_sync import applicant_import
from app.models import (
    Candidate,
    CandidateIdentity,
    Job,
    JobCandidate,
    OdooApplicantSync,
    OdooJobSync,
)


class FakeStorage:
    def __init__(self):
        self.objects = []

    def store_source_document(
        self,
        *,
        event_id,
        attachment_id,
        filename,
        data,
        content_type,
    ):
        self.objects.append(
            {
                "event_id": event_id,
                "attachment_id": attachment_id,
                "filename": filename,
                "data": data,
                "content_type": content_type,
            }
        )
        return f"candidate-ingestion/{event_id}/source/{attachment_id}/{filename}"


class FakeOdooClient:
    def __init__(self, *, include_resume=True):
        self.include_resume = include_resume
        self.calls = []

    def fields_get(self, model, **_kwargs):
        if model == "hr.applicant":
            return {
                "name": {"type": "char"},
                "partner_name": {"type": "char"},
                "email_from": {"type": "char"},
                "partner_phone": {"type": "char"},
                "linkedin_profile": {"type": "char"},
                "job_id": {"type": "many2one", "relation": "hr.job"},
                "stage_id": {"type": "many2one", "relation": "hr.recruitment.stage"},
                "message_main_attachment_id": {
                    "type": "many2one",
                    "relation": "ir.attachment",
                },
                "create_date": {"type": "datetime"},
                "write_date": {"type": "datetime"},
            }
        if model == "ir.attachment":
            return {
                "name": {"type": "char"},
                "mimetype": {"type": "char"},
                "create_date": {"type": "datetime"},
                "res_model": {"type": "char"},
                "res_id": {"type": "integer"},
                "datas": {"type": "binary"},
            }
        raise AssertionError(model)

    def search_read(
        self,
        model,
        domain,
        *,
        fields=None,
        limit=None,
        offset=None,
        order=None,
    ):
        self.calls.append(
            {
                "model": model,
                "domain": domain,
                "fields": fields,
                "limit": limit,
                "offset": offset,
                "order": order,
            }
        )
        if model == "hr.applicant":
            # A cursor condition means the first row was already consumed.
            if any(
                isinstance(item, list)
                and len(item) >= 3
                and item[0] == "write_date"
                for item in domain
            ):
                return []
            return [
                {
                    "id": 501,
                    "name": "Aplicación de Ana Pérez",
                    "partner_name": "Ana Pérez",
                    "email_from": "ANA@example.com",
                    "partner_phone": "+57 300 123 4567",
                    "linkedin_profile": "https://linkedin.example/ana",
                    "job_id": [34, "Cloud Engineer"],
                    "stage_id": [1, "New"],
                    "message_main_attachment_id": [91, "ana_cv.pdf"]
                    if self.include_resume
                    else False,
                    "create_date": "2026-10-07 12:00:00",
                    "write_date": "2026-10-07 12:05:00",
                }
            ]

        if model == "ir.attachment":
            if not self.include_resume:
                return []
            id_filter = next(
                (
                    item
                    for item in domain
                    if isinstance(item, list)
                    and len(item) >= 3
                    and item[0] == "id"
                ),
                None,
            )
            if id_filter is not None:
                if "datas" in (fields or []):
                    return [
                        {
                            "id": 91,
                            "name": "ana_cv.pdf",
                            "mimetype": "application/pdf",
                            "datas": base64.b64encode(b"%PDF-1.4\nresume").decode("ascii"),
                        }
                    ]
                return [
                    {
                        "id": 91,
                        "name": "ana_cv.pdf",
                        "mimetype": "application/pdf",
                        "create_date": "2026-10-07 12:00:00",
                    }
                ]
            return []

        raise AssertionError(model)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Candidate.__table__,
            CandidateIdentity.__table__,
            Job.__table__,
            JobCandidate.__table__,
            OdooJobSync.__table__,
            OdooApplicantSync.__table__,
            CandidateIngestionEvent.__table__,
            CandidateIngestionDocument.__table__,
            CandidateIngestionCursor.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _mapped_job(db):
    job = Job(
        title="Cloud Engineer",
        description="AWS y Python",
        owner_sub="owner-1",
        status="ACTIVE",
    )
    db.add(job)
    db.flush()
    db.add(
        OdooJobSync(
            job_id=job.id,
            idempotency_key=f"job:{job.id}",
            payload={},
            status="SYNCED",
            odoo_record_id="34",
        )
    )
    db.commit()
    return job


def test_imports_applicant_resume_and_binds_existing_odoo_record(db, monkeypatch):
    job = _mapped_job(db)
    client = FakeOdooClient(include_resume=True)
    storage = FakeStorage()
    dispatched = []
    monkeypatch.setattr(
        applicant_import.queue,
        "send_candidate_ingestion",
        lambda event_id: dispatched.append(event_id),
    )

    result = applicant_import.sync_applicants_from_odoo(
        db,
        client=client,
        storage=storage,
    )

    assert result["jobs_scanned"] == 1
    assert result["discovered"] == 1
    assert result["created"] == 1
    assert result["with_resume"] == 1
    assert result["without_resume"] == 0

    candidate = db.query(Candidate).one()
    assert candidate.name == "Ana Pérez"
    assert candidate.email == "ana@example.com"
    assert candidate.metadata_["odoo_applicant_id"] == "501"
    assert candidate.metadata_["contact"]["phone"] == "+57 300 123 4567"

    application = db.query(JobCandidate).one()
    assert application.job_id == job.id
    assert application.candidate_id == candidate.id
    assert application.application_status == "APPLIED"

    sync = db.query(OdooApplicantSync).one()
    assert sync.job_candidate_id == application.id
    assert sync.odoo_job_id == "34"
    assert sync.odoo_applicant_id == "501"
    assert sync.status == "SYNCED"

    event = db.query(CandidateIngestionEvent).one()
    assert event.job_id == job.id
    assert event.candidate_id == candidate.id
    assert event.status == "STORED"
    assert event.queue_dispatched_at is not None
    assert dispatched == [event.id]

    document = db.query(CandidateIngestionDocument).one()
    assert document.filename == "ana_cv.pdf"
    assert document.content_type == "application/pdf"
    assert len(storage.objects) == 1

    cursor = db.query(CandidateIngestionCursor).one()
    assert '"id":501' in cursor.cursor_value

    second = applicant_import.sync_applicants_from_odoo(
        db,
        client=client,
        storage=storage,
    )
    assert second["discovered"] == 0
    assert db.query(Candidate).count() == 1
    assert db.query(JobCandidate).count() == 1
    assert db.query(CandidateIngestionEvent).count() == 1


def test_imports_candidate_without_resume_and_marks_review(db, monkeypatch):
    _mapped_job(db)
    client = FakeOdooClient(include_resume=False)
    storage = FakeStorage()
    monkeypatch.setattr(
        applicant_import.queue,
        "send_candidate_ingestion",
        lambda _event_id: pytest.fail("No queue message expected without a resume"),
    )

    result = applicant_import.sync_applicants_from_odoo(
        db,
        client=client,
        storage=storage,
    )

    assert result["created"] == 1
    assert result["with_resume"] == 0
    assert result["without_resume"] == 1
    assert result["needs_review"] == 1
    assert db.query(Candidate).count() == 1
    assert db.query(JobCandidate).count() == 1

    event = db.query(CandidateIngestionEvent).one()
    assert event.status == "NEEDS_REVIEW"
    assert event.last_error_code == "RESUME_ATTACHMENT_MISSING"
    assert db.query(CandidateIngestionDocument).count() == 0
    assert storage.objects == []
