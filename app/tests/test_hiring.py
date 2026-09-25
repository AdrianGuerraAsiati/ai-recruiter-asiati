"""End-to-end service coverage for candidate hiring into onboarding."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.access_control import ensure_rbac_catalog
from app.db import Base
from app.domains.hiring import service as hiring_service
from app.domains.training import service as training_service
from app.models import Candidate, Job, JobCandidate, TrainingAssignment, UserProfile


class FakeCognito:
    def __init__(self):
        self.created = []

    def admin_create_user(self, *, UserPoolId, Username, UserAttributes, DesiredDeliveryMediums):
        self.created.append(Username)
        return {
            "User": {
                "Attributes": [
                    {"Name": "sub", "Value": f"sub-{Username}"},
                    *UserAttributes,
                ]
            }
        }

    def admin_get_user(self, *, UserPoolId, Username):
        return {
            "Username": Username,
            "UserAttributes": [
                {"Name": "sub", "Value": f"sub-{Username}"},
                {"Name": "email", "Value": Username},
            ],
        }

    def admin_delete_user(self, *, UserPoolId, Username):
        return {}


@pytest.fixture()
def db(monkeypatch):
    monkeypatch.setenv("COGNITO_USER_POOL_ID", "test-pool")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    ensure_rbac_catalog(session)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _application(db, *, email="ana@example.com", banned=False):
    job = Job(
        title="Backend Developer",
        description="Python",
        owner_sub="admin-sub",
    )
    candidate = Candidate(
        name="Ana Pérez",
        email=email,
        owner_sub="admin-sub",
        is_banned=banned,
    )
    db.add_all([job, candidate])
    db.flush()
    link = JobCandidate(
        job_id=job.id,
        candidate_id=candidate.id,
        application_status="OFFER",
    )
    db.add(link)
    db.commit()
    db.refresh(job)
    db.refresh(candidate)
    db.refresh(link)
    return job, candidate, link


def _hire(db, *, cognito, job, candidate):
    return hiring_service.hire_candidate(
        db,
        owner_sub="admin-sub",
        job_id=job.id,
        candidate_id=candidate.id,
        created_by_sub="admin-sub",
        department="Tecnología",
        cognito_client=cognito,
    )


def test_hire_creates_employee_marks_application_and_assigns_onboarding(db):
    job, candidate, link = _application(db)
    cognito = FakeCognito()

    result = _hire(
        db,
        cognito=cognito,
        job=job,
        candidate=candidate,
    )

    db.refresh(link)
    employee = db.query(UserProfile).one()
    assignment = db.query(TrainingAssignment).one()

    assert result["application_status"] == "HIRED"
    assert result["status_changed"] is True
    assert result["employee_created"] is True
    assert link.application_status == "HIRED"
    assert link.employee_id == employee.id
    assert link.hired_at is not None
    assert employee.email == "ana@example.com"
    assert employee.first_name == "Ana"
    assert employee.last_name == "Pérez"
    assert employee.job_title == "Backend Developer"
    assert employee.department == "Tecnología"
    assert employee.onboarding_status == "PENDING"
    assert employee.onboarding_started_at is None
    assert assignment.employee_id == employee.id
    assert assignment.course.status == "PUBLISHED"
    assert assignment.course.title == "Onboarding ASIATI"
    assert result["onboarding_assignment"]["course"]["progress_percent"] == 0
    assert cognito.created == ["ana@example.com"]


def test_hire_is_idempotent_for_same_application(db):
    job, candidate, link = _application(db)
    cognito = FakeCognito()

    first = _hire(db, cognito=cognito, job=job, candidate=candidate)
    second = _hire(db, cognito=cognito, job=job, candidate=candidate)

    assert first["employee"]["id"] == second["employee"]["id"]
    assert first["onboarding_assignment"]["id"] == second["onboarding_assignment"]["id"]
    assert second["employee_created"] is False
    assert second["status_changed"] is False
    assert db.query(UserProfile).count() == 1
    assert db.query(TrainingAssignment).count() == 1
    assert cognito.created == ["ana@example.com"]
    db.refresh(link)
    assert link.application_status == "HIRED"


def test_same_candidate_hired_for_two_jobs_reuses_employee_and_onboarding(db):
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
        application_status="OFFER",
    )
    db.add(second_link)
    db.commit()
    db.refresh(second_job)
    db.refresh(second_link)

    cognito = FakeCognito()
    first = _hire(
        db,
        cognito=cognito,
        job=first_job,
        candidate=candidate,
    )
    second = hiring_service.hire_candidate(
        db,
        owner_sub="admin-sub",
        job_id=second_job.id,
        candidate_id=candidate.id,
        created_by_sub="admin-sub",
        department="Tecnología",
        cognito_client=cognito,
    )

    db.refresh(first_link)
    db.refresh(second_link)

    assert first["employee"]["id"] == second["employee"]["id"]
    assert first["onboarding_assignment"]["id"] == second["onboarding_assignment"]["id"]
    assert first_link.employee_id == second_link.employee_id == first["employee"]["id"]
    assert first_link.application_status == "HIRED"
    assert second_link.application_status == "HIRED"
    assert first_link.hired_at is not None
    assert second_link.hired_at is not None
    assert db.query(UserProfile).count() == 1
    assert db.query(TrainingAssignment).count() == 1
    assert cognito.created == ["ana@example.com"]


def test_hired_employee_onboarding_moves_pending_to_in_progress_to_completed(db):
    job, candidate, _ = _application(db)
    result = _hire(
        db,
        cognito=FakeCognito(),
        job=job,
        candidate=candidate,
    )
    employee_id = result["employee"]["id"]
    course_id = result["onboarding_assignment"]["course"]["id"]

    employee = db.query(UserProfile).filter(UserProfile.id == employee_id).one()
    assert employee.onboarding_status == "PENDING"

    course_payload = training_service.get_my_course(
        db,
        employee_id=employee_id,
        course_id=course_id,
    )
    required_lessons = [
        lesson
        for module in course_payload["course"]["modules"]
        for lesson in module["lessons"]
        if not lesson["is_optional"]
    ]
    assert required_lessons

    first = required_lessons[0]
    if first["content_type"] == "CHECKLIST":
        training_service.update_checklist_progress(
            db,
            employee_id=employee_id,
            lesson_id=first["id"],
            completed_items=list(range(len(first["checklist_items"]))),
        )
    else:
        training_service.complete_lesson(
            db,
            employee_id=employee_id,
            lesson_id=first["id"],
        )

    db.refresh(employee)
    assert employee.onboarding_status == "IN_PROGRESS"
    assert employee.onboarding_started_at is not None
    assert employee.onboarding_completed_at is None

    for lesson in required_lessons[1:]:
        if lesson["content_type"] == "CHECKLIST":
            training_service.update_checklist_progress(
                db,
                employee_id=employee_id,
                lesson_id=lesson["id"],
                completed_items=list(range(len(lesson["checklist_items"]))),
            )
        else:
            training_service.complete_lesson(
                db,
                employee_id=employee_id,
                lesson_id=lesson["id"],
            )

    assignment = (
        db.query(TrainingAssignment)
        .filter(
            TrainingAssignment.employee_id == employee_id,
            TrainingAssignment.course_id == course_id,
        )
        .one()
    )
    answers = {
        question.id: question.correct_option
        for question in assignment.course.quiz.questions
    }
    result = training_service.submit_quiz_attempt(
        db,
        employee_id=employee_id,
        course_id=course_id,
        answers=answers,
    )

    db.refresh(employee)
    db.refresh(assignment)
    assert result["assignment_status"] == "COMPLETED"
    assert assignment.status == "COMPLETED"
    assert employee.onboarding_status == "COMPLETED"
    assert employee.onboarding_completed_at is not None


def test_hire_requires_candidate_email(db):
    job, candidate, _ = _application(db, email=None)

    with pytest.raises(hiring_service.HiringValidationError):
        _hire(
            db,
            cognito=FakeCognito(),
            job=job,
            candidate=candidate,
        )


def test_banned_candidate_cannot_be_hired(db):
    job, candidate, _ = _application(db, banned=True)

    with pytest.raises(hiring_service.HiringConflictError):
        _hire(
            db,
            cognito=FakeCognito(),
            job=job,
            candidate=candidate,
        )
