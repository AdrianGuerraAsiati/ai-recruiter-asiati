"""End-to-end service coverage for candidate hiring into onboarding."""

import pytest
from botocore.exceptions import ClientError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.access_control import ensure_rbac_catalog
from app.db import Base
from app.domains.hiring import service as hiring_service
from app.domains.training import service as training_service
from app.domains.training import video_progress as training_video_progress
from app.models import (
    Candidate,
    Job,
    JobCandidate,
    OdooApplicantSync,
    OdooEmployeeSync,
    TrainingAssignment,
    UserProfile,
)


class FakeCognito:
    def __init__(self):
        self.created = []

    def admin_create_user(self, *, UserPoolId, Username, UserAttributes, TemporaryPassword, MessageAction):
        self.created.append(Username)
        assert TemporaryPassword
        assert MessageAction == "SUPPRESS"
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


class ExistingCognitoUser(FakeCognito):
    def admin_create_user(self, *, UserPoolId, Username, UserAttributes, TemporaryPassword, MessageAction):
        self.created.append(Username)
        raise ClientError(
            {
                "Error": {
                    "Code": "UsernameExistsException",
                    "Message": "User already exists",
                }
            },
            "AdminCreateUser",
        )


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
        metadata_={"phone": "+57 300 123 4567"},
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
        username="ana.perez",
        department="Tecnología",
        cognito_client=cognito,
    )


def test_hire_creates_employee_marks_application_and_assigns_onboarding(db, monkeypatch):
    job, candidate, link = _application(db)
    cognito = FakeCognito()
    delivered = []

    def fake_delivery(_db, *, employee_id, client=None):
        delivered.append(employee_id)
        return {"status": "SYNCED", "action": "CREATED"}

    monkeypatch.setattr(
        hiring_service.employee_delivery, "sync_employee_now", fake_delivery
    )

    result = _hire(
        db,
        cognito=cognito,
        job=job,
        candidate=candidate,
    )

    db.refresh(link)
    employee = db.query(UserProfile).one()
    assignment = db.query(TrainingAssignment).one()
    applicant_sync = db.query(OdooApplicantSync).one()
    odoo_sync = db.query(OdooEmployeeSync).one()

    assert result["application_status"] == "HIRED"
    assert result["status_changed"] is True
    assert result["employee_created"] is True
    assert link.application_status == "HIRED"
    assert link.employee_id == employee.id
    assert link.hired_at is not None
    assert employee.email == "ana@example.com"
    assert employee.login_username == "ana.perez"
    assert result["credentials"]["username"] == "ana.perez"
    assert result["credentials"]["temporary_password"]
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
    assert result["odoo_applicant_sync"]["status"] == "PENDING"
    assert result["odoo_applicant_sync"]["job_candidate_id"] == link.id
    assert applicant_sync.payload["operation"] == "UPSERT_APPLICANT"
    assert applicant_sync.payload["source"]["application_status"] == "HIRED"
    assert result["odoo_sync"]["status"] == "PENDING"
    assert result["odoo_sync"]["idempotency_key"] == f"employee:{employee.id}"
    assert result["odoo_delivery"]["status"] == "SYNCED"
    assert result["odoo_delivery"]["action"] == "CREATED"
    assert delivered == [employee.id]
    assert odoo_sync.employee_id == employee.id
    assert odoo_sync.source_job_candidate_id == link.id
    assert odoo_sync.payload["operation"] == "UPSERT_EMPLOYEE"
    assert odoo_sync.payload["source"]["candidate_id"] == candidate.id
    assert odoo_sync.payload["source"]["job_id"] == job.id
    assert odoo_sync.payload["employee"]["email"] == "ana@example.com"
    assert odoo_sync.payload["candidate"]["phone"] == "+57 300 123 4567"
    assert cognito.created == ["ana@example.com"]


def test_hire_materializes_existing_cognito_user_and_continues_onboarding(db):
    job, candidate, link = _application(db, email="existing@example.com")
    cognito = ExistingCognitoUser()

    result = _hire(
        db,
        cognito=cognito,
        job=job,
        candidate=candidate,
    )

    db.refresh(link)
    employee = db.query(UserProfile).one()
    assignment = db.query(TrainingAssignment).one()

    assert result["employee_created"] is False
    assert result["application_status"] == "HIRED"
    assert link.employee_id == employee.id
    assert employee.cognito_sub == "sub-existing@example.com"
    assert employee.email == "existing@example.com"
    assert employee.first_name == "Ana"
    assert employee.last_name == "Pérez"
    assert employee.job_title == "Backend Developer"
    assert employee.department == "Tecnología"
    assert employee.onboarding_status == "PENDING"
    assert assignment.employee_id == employee.id
    assert db.query(UserProfile).count() == 1
    assert db.query(TrainingAssignment).count() == 1
    assert cognito.created == ["existing@example.com"]


def test_admin_can_hire_candidate_created_by_another_admin(db):
    job, candidate, link = _application(db)
    cognito = FakeCognito()

    result = hiring_service.hire_candidate(
        db,
        owner_sub="other-admin-sub",
        job_id=job.id,
        candidate_id=candidate.id,
        created_by_sub="other-admin-sub",
        username="ana.perez",
        department="Tecnología",
        cognito_client=cognito,
    )

    db.refresh(link)
    assert result["application_status"] == "HIRED"
    assert link.application_status == "HIRED"
    assert result["employee_created"] is True


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
    assert db.query(OdooApplicantSync).count() == 1
    assert db.query(OdooEmployeeSync).count() == 1
    assert first["odoo_applicant_sync"]["id"] == second["odoo_applicant_sync"]["id"]
    assert first["odoo_sync"]["id"] == second["odoo_sync"]["id"]
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
        username="ana.perez",
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
    assert db.query(OdooApplicantSync).count() == 2
    assert db.query(OdooEmployeeSync).count() == 1
    odoo_sync = db.query(OdooEmployeeSync).one()
    assert odoo_sync.source_job_candidate_id == second_link.id
    assert odoo_sync.payload["source"]["job_id"] == second_job.id
    assert cognito.created == ["ana@example.com"]



def _complete_required_lesson(db, *, employee_id: str, lesson: dict) -> None:
    if lesson["content_type"] == "CHECKLIST":
        training_service.update_checklist_progress(
            db,
            employee_id=employee_id,
            lesson_id=lesson["id"],
            completed_items=list(range(len(lesson["checklist_items"]))),
        )
        return
    if lesson["content_type"] == "VIDEO":
        duration = float(lesson.get("duration_seconds") or 100)
        target = duration * 0.80
        start = 0.0
        while start < target:
            end = min(start + 20.0, target)
            training_video_progress.update_video_progress(
                db,
                employee_id=employee_id,
                lesson_id=lesson["id"],
                duration_seconds=duration,
                played_from_seconds=start,
                played_to_seconds=end,
                position_seconds=end,
            )
            start = end
        return
    training_service.complete_lesson(
        db,
        employee_id=employee_id,
        lesson_id=lesson["id"],
    )


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
    _complete_required_lesson(db, employee_id=employee_id, lesson=first)

    db.refresh(employee)
    assert employee.onboarding_status == "IN_PROGRESS"
    assert employee.onboarding_started_at is not None
    assert employee.onboarding_completed_at is None

    for lesson in required_lessons[1:]:
        _complete_required_lesson(db, employee_id=employee_id, lesson=lesson)

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


def test_hire_survives_odoo_delivery_failure(db, monkeypatch):
    job, candidate, link = _application(db)

    def failed_delivery(_db, *, employee_id, client=None):
        raise hiring_service.employee_delivery.OdooEmployeeDeliveryError("Odoo unavailable")

    monkeypatch.setattr(
        "app.domains.hiring.service.employee_delivery.sync_employee_now",
        failed_delivery,
    )

    result = _hire(db, cognito=FakeCognito(), job=job, candidate=candidate)

    db.refresh(link)
    employee = db.query(UserProfile).one()
    sync = db.query(OdooEmployeeSync).one()
    assert result["application_status"] == "HIRED"
    assert result["odoo_delivery"] is None
    assert link.employee_id == employee.id
    assert db.query(TrainingAssignment).count() == 1
    assert sync.status == "PENDING"
