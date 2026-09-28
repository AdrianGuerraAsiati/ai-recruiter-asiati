"""Odoo synchronization contracts for selected applications."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.domains.candidates import service as candidates_service
from app.models import Candidate, Job, JobCandidate, OdooApplicantSync


@pytest.fixture()
def db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _application(db, *, job_title="Backend Developer"):
    job = Job(
        title=job_title,
        description="Python",
        owner_sub="admin-sub",
        country_code="CO",
        city="Bogotá",
        employment_type="FULL_TIME",
        response_time_business_days=2,
        phone_call_count=1,
        onsite_interview_count=1,
        offer_wait_days=4,
        offer_wait_reference="AFTER_INTERVIEW",
    )
    candidate = Candidate(
        name="Ana Pérez",
        email="ana@example.com",
        owner_sub="admin-sub",
        metadata_={"phone": "+573001112233", "filename": "ana.pdf"},
    )
    db.add_all([job, candidate])
    db.flush()
    link = JobCandidate(
        job_id=job.id,
        candidate_id=candidate.id,
        application_status="SCREENING",
    )
    db.add(link)
    db.commit()
    return job, candidate, link


def test_selected_application_creates_idempotent_odoo_applicant_outbox(db, monkeypatch):
    job, candidate, link = _application(db)
    monkeypatch.setattr(
        "app.domains.indeed.service.queue_candidate_status",
        lambda *args, **kwargs: None,
    )

    current, changed = candidates_service.set_application_status(
        db,
        job_id=job.id,
        candidate_id=candidate.id,
        status="SELECTED",
        owner_sub="other-admin-sub",
    )

    sync = db.query(OdooApplicantSync).one()
    assert changed is True
    assert current.application_status == "SELECTED"
    assert sync.job_candidate_id == link.id
    assert sync.idempotency_key == f"application:{link.id}"
    assert sync.status == "PENDING"
    assert sync.payload["operation"] == "UPSERT_APPLICANT"
    assert sync.payload["candidate"] == {
        "external_id": candidate.id,
        "name": "Ana Pérez",
        "email": "ana@example.com",
        "phone": "+573001112233",
    }
    assert sync.payload["documents"]["candidate_cv"] == {
        "candidate_id": candidate.id,
        "source": "CANONICAL_CANDIDATE_DOCUMENT",
    }
    assert sync.payload["job"]["external_id"] == job.id
    assert sync.payload["job"]["selection_process"] == {
        "response_time_business_days": 2,
        "steps": [
            {"type": "PHONE_CALL", "quantity": 1},
            {"type": "ONSITE_INTERVIEW", "quantity": 1},
        ],
        "offer_wait_days": 4,
        "offer_wait_reference": "AFTER_INTERVIEW",
    }

    current_again, changed_again = candidates_service.set_application_status(
        db,
        job_id=job.id,
        candidate_id=candidate.id,
        status="SELECTED",
        owner_sub="admin-sub",
    )
    assert current_again.id == current.id
    assert changed_again is False
    assert db.query(OdooApplicantSync).count() == 1


def test_same_candidate_selected_for_two_jobs_has_two_odoo_applicant_states(db, monkeypatch):
    first_job, candidate, first_link = _application(db)
    second_job = Job(
        title="Platform Engineer",
        description="Cloud",
        owner_sub="admin-sub",
    )
    db.add(second_job)
    db.flush()
    second_link = JobCandidate(
        job_id=second_job.id,
        candidate_id=candidate.id,
        application_status="SCREENING",
    )
    db.add(second_link)
    db.commit()

    monkeypatch.setattr(
        "app.domains.indeed.service.queue_candidate_status",
        lambda *args, **kwargs: None,
    )

    for job in (first_job, second_job):
        candidates_service.set_application_status(
            db,
            job_id=job.id,
            candidate_id=candidate.id,
            status="SELECTED",
            owner_sub="admin-sub",
        )

    syncs = db.query(OdooApplicantSync).order_by(OdooApplicantSync.job_candidate_id).all()
    assert len(syncs) == 2
    assert {sync.job_candidate_id for sync in syncs} == {first_link.id, second_link.id}
    assert len({sync.idempotency_key for sync in syncs}) == 2


def test_non_selected_status_does_not_create_odoo_applicant_outbox(db, monkeypatch):
    job, candidate, _link = _application(db)
    monkeypatch.setattr(
        "app.domains.indeed.service.queue_candidate_status",
        lambda *args, **kwargs: None,
    )

    candidates_service.set_application_status(
        db,
        job_id=job.id,
        candidate_id=candidate.id,
        status="INTERVIEW",
        owner_sub="admin-sub",
    )

    assert db.query(OdooApplicantSync).count() == 0
