"""Psychotechnical assessment service tests."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.domains.psychotechnical import catalog, service
from app.domains.psychotechnical.models import PsychotechnicalAssignment
from app.models import Candidate, Job


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Candidate.__table__,
            Job.__table__,
            PsychotechnicalAssignment.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _candidate(db):
    row = Candidate(name="Ana Prueba", email="ana@example.com", owner_sub="admin")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _job(db):
    row = Job(title="Analista de Datos", description="Python", owner_sub="admin")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _all_correct_answers():
    return [
        {
            "question_id": question["id"],
            "option_id": question["correct"],
        }
        for question in catalog.QUESTIONS
    ]


def test_create_assignment_returns_secret_token_without_storing_it_raw(db):
    candidate = _candidate(db)
    job = _job(db)

    assignment, token = service.create_assignment(
        db,
        candidate_id=candidate.id,
        job_id=job.id,
        expires_days=7,
        created_by_sub="admin-sub",
    )

    assert token
    assert assignment.token_hash != token
    assert len(assignment.token_hash) == 64
    assert assignment.status == "PENDING"
    assert assignment.test_key == catalog.TEST_KEY

    public = service.public_assignment(db, token)
    assert public["candidate_name"] == "Ana Prueba"
    assert public["job_title"] == "Analista de Datos"
    assert public["question_count"] == 12


def test_public_start_never_exposes_correct_answers(db):
    candidate = _candidate(db)
    assignment, token = service.create_assignment(
        db,
        candidate_id=candidate.id,
        job_id=None,
        expires_days=7,
        created_by_sub="admin-sub",
    )

    payload = service.start_assignment(db, token)

    assert payload["assignment"]["status"] == "IN_PROGRESS"
    assert len(payload["questions"]) == len(catalog.QUESTIONS)
    assert all("correct" not in question for question in payload["questions"])

    db.refresh(assignment)
    assert assignment.started_at is not None


def test_submit_scores_all_objective_dimensions(db):
    candidate = _candidate(db)
    assignment, token = service.create_assignment(
        db,
        candidate_id=candidate.id,
        job_id=None,
        expires_days=7,
        created_by_sub="admin-sub",
    )
    service.start_assignment(db, token)

    result = service.submit_assignment(db, token, _all_correct_answers())

    assert result["status"] == "COMPLETED"
    db.refresh(assignment)
    assert assignment.status == "COMPLETED"
    assert assignment.score_total == 100
    assert {
        item["score"]
        for item in assignment.dimension_scores.values()
    } == {100}
    assert len(assignment.answers) == len(catalog.QUESTIONS)


def test_submit_requires_every_question_exactly_once(db):
    candidate = _candidate(db)
    _assignment, token = service.create_assignment(
        db,
        candidate_id=candidate.id,
        job_id=None,
        expires_days=7,
        created_by_sub="admin-sub",
    )

    with pytest.raises(service.PsychotechnicalConflict):
        service.submit_assignment(db, token, _all_correct_answers()[:-1])


def test_duplicate_active_assignment_is_rejected(db):
    candidate = _candidate(db)
    service.create_assignment(
        db,
        candidate_id=candidate.id,
        job_id=None,
        expires_days=7,
        created_by_sub="admin-sub",
    )

    with pytest.raises(service.PsychotechnicalConflict):
        service.create_assignment(
            db,
            candidate_id=candidate.id,
            job_id=None,
            expires_days=7,
            created_by_sub="admin-sub",
        )


def test_expired_assignment_is_reported_as_expired(db):
    candidate = _candidate(db)
    assignment, token = service.create_assignment(
        db,
        candidate_id=candidate.id,
        job_id=None,
        expires_days=7,
        created_by_sub="admin-sub",
    )
    assignment.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()

    rows = service.list_assignments(db, status="EXPIRED")
    assert [row["id"] for row in rows] == [assignment.id]

    with pytest.raises(service.PsychotechnicalExpired):
        service.public_assignment(db, token)


def test_regenerate_link_invalidates_previous_token_and_restarts_pending(db):
    candidate = _candidate(db)
    assignment, old_token = service.create_assignment(
        db,
        candidate_id=candidate.id,
        job_id=None,
        expires_days=7,
        created_by_sub="admin-sub",
    )
    service.start_assignment(db, old_token)

    refreshed, new_token = service.regenerate_link(
        db,
        assignment.id,
        expires_days=7,
    )

    assert new_token != old_token
    assert refreshed.status == "PENDING"
    assert refreshed.started_at is None

    with pytest.raises(service.PsychotechnicalNotFound):
        service.public_assignment(db, old_token)

    assert service.public_assignment(db, new_token)["status"] == "PENDING"


def test_banned_candidate_cannot_receive_psychotechnical_assignment(db):
    candidate = _candidate(db)
    candidate.is_banned = True
    db.commit()

    with pytest.raises(service.PsychotechnicalConflict):
        service.create_assignment(
            db,
            candidate_id=candidate.id,
            job_id=None,
            expires_days=7,
            created_by_sub="admin-sub",
        )
