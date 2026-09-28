"""Recruitment calendar domain coverage."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.domains.recruitment_calendar import service
from app.domains.recruitment_calendar.exceptions import (
    RecruitmentApplicationNotEligible,
)
from app.models import Candidate, Job, JobCandidate, RecruitmentEvent


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _application(db, *, status="SELECTED", suffix="one"):
    job = Job(
        title=f"Ejecutivo Comercial {suffix}",
        owner_sub="admin-a",
    )
    candidate = Candidate(
        name=f"Candidato {suffix}",
        email=f"{suffix}@example.com",
        owner_sub="admin-a",
    )
    db.add_all([job, candidate])
    db.flush()
    link = JobCandidate(
        job_id=job.id,
        candidate_id=candidate.id,
        application_status=status,
    )
    db.add(link)
    db.commit()
    db.refresh(job)
    db.refresh(candidate)
    db.refresh(link)
    return job, candidate, link


def test_selected_candidate_can_receive_phone_call(db):
    job, candidate, _link = _application(db)
    start = datetime(2026, 10, 2, 15, 0, tzinfo=timezone.utc)
    end = start + timedelta(minutes=30)

    payload = service.create_event(
        db,
        job_id=job.id,
        candidate_id=candidate.id,
        kind="PHONE_CALL",
        starts_at=start,
        ends_at=end,
        location=None,
        notes="Primera llamada",
        created_by_sub="talent-sub",
    )

    assert payload["kind"] == "PHONE_CALL"
    assert payload["status"] == "SCHEDULED"
    assert payload["candidate"]["candidate_id"] == candidate.id
    assert payload["job"]["job_id"] == job.id
    assert db.query(RecruitmentEvent).count() == 1


def test_screening_candidate_must_be_selected_before_scheduling(db):
    job, candidate, _link = _application(db, status="SCREENING")
    start = datetime(2026, 10, 2, 15, 0, tzinfo=timezone.utc)

    with pytest.raises(
        RecruitmentApplicationNotEligible,
        match="Selecciona al candidato",
    ):
        service.create_event(
            db,
            job_id=job.id,
            candidate_id=candidate.id,
            kind="PHONE_CALL",
            starts_at=start,
            ends_at=start + timedelta(minutes=30),
            location=None,
            notes=None,
            created_by_sub="talent-sub",
        )


def test_calendar_lists_only_eligible_applications(db):
    selected_job, selected_candidate, _ = _application(
        db,
        status="SELECTED",
        suffix="selected",
    )
    _application(db, status="SCREENING", suffix="screening")

    items = service.list_eligible_applications(db)

    assert len(items) == 1
    assert items[0]["candidate"]["candidate_id"] == selected_candidate.id
    assert items[0]["job"]["job_id"] == selected_job.id


def test_calendar_filters_overlapping_window_and_updates_status(db):
    job, candidate, _link = _application(db)
    start = datetime(2026, 10, 5, 14, 0, tzinfo=timezone.utc)
    created = service.create_event(
        db,
        job_id=job.id,
        candidate_id=candidate.id,
        kind="ONSITE_INTERVIEW",
        starts_at=start,
        ends_at=start + timedelta(hours=1),
        location="Oficina ASIATI",
        notes=None,
        created_by_sub="talent-sub",
    )

    items = service.list_events(
        db,
        ends_after=start - timedelta(minutes=15),
        starts_before=start + timedelta(minutes=15),
    )
    assert [item["id"] for item in items] == [created["id"]]

    updated = service.update_event(
        db,
        created["id"],
        changes={"status": "COMPLETED", "notes": "Entrevista realizada"},
    )
    assert updated["status"] == "COMPLETED"
    assert updated["notes"] == "Entrevista realizada"


def test_calendar_rejects_invalid_time_window(db):
    job, candidate, _link = _application(db)
    start = datetime(2026, 10, 5, 14, 0, tzinfo=timezone.utc)

    with pytest.raises(service.RecruitmentEventValidationError):
        service.create_event(
            db,
            job_id=job.id,
            candidate_id=candidate.id,
            kind="ONSITE_INTERVIEW",
            starts_at=start,
            ends_at=start,
            location="Oficina",
            notes=None,
            created_by_sub="talent-sub",
        )
