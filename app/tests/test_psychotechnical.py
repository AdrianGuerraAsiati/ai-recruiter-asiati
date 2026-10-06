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


def _create(db, candidate, *, test_key=catalog.COMMON_SENSE, job=None):
    return service.create_assignment(
        db,
        candidate_id=candidate.id,
        job_id=job.id if job else None,
        test_key=test_key,
        expires_days=7,
        created_by_sub="admin-sub",
    )


def _all_common_sense_correct():
    return [
        {
            "question_id": question["id"],
            "option_id": question["correct"],
        }
        for question in catalog.TESTS[catalog.COMMON_SENSE]["questions"]
    ]


def test_catalog_contains_the_four_asiati_source_tests():
    payload = catalog.catalog_payload()

    assert {item["key"] for item in payload} == {
        catalog.COMMON_SENSE,
        catalog.TEMPERAMENT,
        catalog.VALANTI,
        catalog.ATTENTION,
    }
    assert {item["code"] for item in payload} >= {
        "GTH-F-016",
        "GTH-F-017",
        "VALANTI",
        "ATENCIÓN-DETALLE",
    }


def test_create_assignment_returns_secret_token_without_storing_it_raw(db):
    candidate = _candidate(db)
    job = _job(db)

    assignment, token = _create(
        db,
        candidate,
        test_key=catalog.COMMON_SENSE,
        job=job,
    )

    assert token
    assert assignment.token_hash != token
    assert len(assignment.token_hash) == 64
    assert assignment.status == "PENDING"
    assert assignment.test_key == catalog.COMMON_SENSE

    public = service.public_assignment(db, token)
    assert public["candidate_name"] == "Ana Prueba"
    assert public["job_title"] == "Analista de Datos"
    assert public["test_code"] == "GTH-F-016"
    assert public["question_count"] == 10


def test_public_start_never_exposes_correct_answers(db):
    candidate = _candidate(db)
    assignment, token = _create(db, candidate, test_key=catalog.COMMON_SENSE)

    payload = service.start_assignment(db, token)

    assert payload["assignment"]["status"] == "IN_PROGRESS"
    assert len(payload["questions"]) == 10
    assert all("correct" not in question for question in payload["questions"])

    db.refresh(assignment)
    assert assignment.started_at is not None


def test_common_sense_scoring_matches_gth_f016_key(db):
    candidate = _candidate(db)
    assignment, token = _create(db, candidate, test_key=catalog.COMMON_SENSE)
    service.start_assignment(db, token)

    result = service.submit_assignment(db, token, _all_common_sense_correct())

    assert result["status"] == "COMPLETED"
    db.refresh(assignment)
    assert assignment.score_total == 100
    assert assignment.dimension_scores["RESULT"]["correct"] == 10
    assert "Excelente criterio" in assignment.dimension_scores["RESULT"]["band"]


def test_common_sense_requires_every_question_once(db):
    candidate = _candidate(db)
    _assignment, token = _create(db, candidate, test_key=catalog.COMMON_SENSE)

    with pytest.raises(service.PsychotechnicalConflict):
        service.submit_assignment(db, token, _all_common_sense_correct()[:-1])


def test_temperament_returns_distribution_not_hiring_score(db):
    candidate = _candidate(db)
    assignment, token = _create(db, candidate, test_key=catalog.TEMPERAMENT)
    questions = catalog.TESTS[catalog.TEMPERAMENT]["questions"]
    answers = [
        {"question_id": question["id"], "option_id": "C"}
        for question in questions
    ]

    service.submit_assignment(db, token, answers)

    db.refresh(assignment)
    assert assignment.score_total is None
    assert assignment.dimension_scores["C"]["count"] == 30
    assert assignment.dimension_scores["C"]["primary"] is True
    assert assignment.dimension_scores["PROFILE"]["profiles"] == ["Melancólico"]
    assert "no se utiliza automáticamente" in assignment.dimension_scores["PROFILE"]["note"]


def test_valanti_uses_pair_allocations_and_returns_five_values(db):
    candidate = _candidate(db)
    assignment, token = _create(db, candidate, test_key=catalog.VALANTI)
    questions = catalog.TESTS[catalog.VALANTI]["questions"]
    answers = [
        {"question_id": question["id"], "option_id": "2-1"}
        for question in questions
    ]

    service.submit_assignment(db, token, answers)

    db.refresh(assignment)
    assert assignment.score_total is None
    assert {
        "TRUTH",
        "RECTITUDE",
        "PEACE",
        "LOVE",
        "NON_VIOLENCE",
        "PROFILE",
    }.issubset(assignment.dimension_scores)
    assert assignment.dimension_scores["TRUTH"]["label"] == "Verdad"
    assert "reference" in assignment.dimension_scores["RECTITUDE"]


def test_attention_accepts_partial_answers_and_scores_efficiency_plus_efficacy(db):
    candidate = _candidate(db)
    assignment, token = _create(db, candidate, test_key=catalog.ATTENTION)
    test = catalog.TESTS[catalog.ATTENTION]
    first = test["questions"][0]
    second = test["questions"][20]
    answers = [
        {"question_id": first["id"], "option_id": first["correct"]},
        {"question_id": second["id"], "option_id": second["correct"]},
    ]

    service.submit_assignment(db, token, answers)

    db.refresh(assignment)
    assert assignment.score_total is not None
    assert assignment.dimension_scores["ALPHANUMERIC"]["answered"] == 1
    assert assignment.dimension_scores["LETTERS"]["answered"] == 1
    assert assignment.dimension_scores["FIGURES"]["answered"] == 0
    assert "method" in assignment.dimension_scores["RESULT"]


def test_duplicate_active_assignment_is_rejected_only_for_same_test(db):
    candidate = _candidate(db)
    _create(db, candidate, test_key=catalog.COMMON_SENSE)

    with pytest.raises(service.PsychotechnicalConflict):
        _create(db, candidate, test_key=catalog.COMMON_SENSE)

    second, _token = _create(db, candidate, test_key=catalog.TEMPERAMENT)
    assert second.test_key == catalog.TEMPERAMENT


def test_expired_assignment_is_reported_as_expired(db):
    candidate = _candidate(db)
    assignment, token = _create(db, candidate, test_key=catalog.COMMON_SENSE)
    assignment.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()

    rows = service.list_assignments(db, status="EXPIRED")
    assert [row["id"] for row in rows] == [assignment.id]

    with pytest.raises(service.PsychotechnicalExpired):
        service.public_assignment(db, token)


def test_regenerate_link_invalidates_previous_token_and_restarts_pending(db):
    candidate = _candidate(db)
    assignment, old_token = _create(db, candidate, test_key=catalog.COMMON_SENSE)
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
        _create(db, candidate, test_key=catalog.COMMON_SENSE)
