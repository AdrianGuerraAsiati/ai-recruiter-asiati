"""End-to-end service coverage for candidate hiring into onboarding."""

import pytest
from botocore.exceptions import ClientError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.access_control import APPLICANT, EMPLOYEE, assign_role, ensure_rbac_catalog
from app.db import Base
from app.domains.hiring import service as hiring_service
from app.domains.employees import service as employees_service
from app.domains.training import service as training_service
from app.domains.training import video_progress as training_video_progress
from app.models import (
    Candidate,
    Job,
    JobCandidate,
    OdooApplicantSync,
    OdooContractSync,
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
        country_code="CO",
        company_name="ASIATI Colombia",
        city="Bogotá",
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
    assert employee.country_code == "CO"
    assert employee.company_name == "ASIATI Colombia"
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
    assert odoo_sync.payload["employee"]["country_code"] == "CO"
    assert odoo_sync.payload["employee"]["company_name"] == "ASIATI Colombia"
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



def test_hire_prepares_employee_contract_for_odoo(db, monkeypatch):
    job, candidate, link = _application(db)
    cognito = FakeCognito()

    def fake_employee_delivery(_db, *, employee_id, client=None):
        return {"status": "SYNCED", "action": "CREATED"}

    monkeypatch.setattr(
        hiring_service.employee_delivery,
        "sync_employee_now",
        fake_employee_delivery,
    )

    result = hiring_service.hire_candidate(
        db,
        owner_sub="admin-sub",
        job_id=job.id,
        candidate_id=candidate.id,
        created_by_sub="admin-sub",
        username="ana.perez",
        department="Tecnología",
        hire_date=None,
        contract={
            "contract_type": "Indefinido",
            "start_date": "2026-10-05",
            "end_date": None,
            "monthly_wage": "3500000",
        },
        cognito_client=cognito,
    )

    employee = db.query(UserProfile).one()
    contract_sync = db.query(OdooContractSync).one()

    assert result["application_status"] == "HIRED"
    assert result["odoo_contract_sync"]["status"] == "PENDING"
    assert result["odoo_contract_sync"]["idempotency_key"] == f"contract:{employee.id}"
    assert result["odoo_contract_delivery"] is None
    assert contract_sync.source_job_candidate_id == link.id
    assert contract_sync.payload["operation"] == "UPSERT_CONTRACT"
    assert contract_sync.payload["contract"]["contract_type"] == "Indefinido"
    assert contract_sync.payload["contract"]["start_date"] == "2026-10-05"
    assert contract_sync.payload["contract"]["monthly_wage"] == "3500000"


def test_hiring_promotes_applicant_login_without_recreating_credentials(db, monkeypatch):
    job, candidate, link = _application(db)
    cognito = FakeCognito()
    applicant = hiring_service.start_candidate_application(
        db,
        owner_sub="admin-sub",
        job_id=job.id,
        candidate_id=candidate.id,
        created_by_sub="admin-sub",
        username="ana.perez",
        cognito_client=cognito,
    )
    profile_id = applicant["employee"]["id"]
    assert employees_service.roles_for_profile(db, profile_id) == [APPLICANT]
    assert employees_service.list_employees(db) == []
    assert db.query(TrainingAssignment).count() == 0

    monkeypatch.setattr(
        hiring_service.employee_delivery, "sync_employee_now",
        lambda _db, *, employee_id: {"status": "SYNCED", "employee_id": employee_id},
    )
    hired = _hire(db, cognito=cognito, job=job, candidate=candidate)
    db.refresh(link)
    assert hired["employee_created"] is False
    assert hired["credentials"] is None
    assert hired["application_status"] == "HIRED"
    assert link.employee_id == profile_id
    assert employees_service.roles_for_profile(db, profile_id) == [EMPLOYEE]
    assert len(employees_service.list_employees(db)) == 1
    assert db.query(TrainingAssignment).count() == 1
    assert cognito.created == ["ana@example.com"]


def test_formal_hire_queues_document_welcome_once_and_never_on_retry(db, monkeypatch):
    job, candidate, link = _application(db)
    deliveries = []

    def fake_welcome(_db, employee_id):
        deliveries.append(employee_id)
        return {"status": "SENT", "attempt_count": 1, "sent_at": "2026-10-12T10:00:00Z"}

    monkeypatch.setattr(hiring_service.document_notifications, "send_welcome", fake_welcome)
    first = _hire(db, cognito=FakeCognito(), job=job, candidate=candidate)
    second = _hire(db, cognito=FakeCognito(), job=job, candidate=candidate)
    assert first["welcome_email"]["status"] == "SENT"
    assert first["status_changed"] is True
    assert second["status_changed"] is False
    assert deliveries == [first["employee"]["id"]]


def test_hire_succeeds_even_when_welcome_email_delivery_fails(db, monkeypatch):
    job, candidate, _link = _application(db)

    def unavailable(*_args, **_kwargs):
        raise RuntimeError("SES unavailable")

    monkeypatch.setattr(hiring_service.document_notifications, "send_welcome", unavailable)
    result = _hire(db, cognito=FakeCognito(), job=job, candidate=candidate)
    assert result["application_status"] == "HIRED"
    assert result["welcome_email"]["status"] == "FAILED"
    assert result["onboarding_assignment"]


def test_hiring_rejects_unverified_odoo_company_without_employee_side_effects(db, monkeypatch):
    job, candidate, link = _application(db)
    from app.domains.odoo_sync import company_catalog
    def invalid_company(*args, **kwargs):
        raise company_catalog.OdooCompanyNotFound("Empresa inactiva en Odoo.")
    monkeypatch.setattr(company_catalog, "require_company", invalid_company)
    cognito = FakeCognito()
    with pytest.raises(hiring_service.HiringValidationError, match="Empresa inactiva"):
        hiring_service.hire_candidate(
            db, owner_sub="admin-sub", job_id=job.id,
            candidate_id=candidate.id, created_by_sub="admin-sub",
            username="ana", odoo_company_id=123, cognito_client=cognito,
        )
    assert cognito.created == []
    assert db.query(OdooEmployeeSync).count() == 0
    assert db.query(UserProfile).count() == 0
    db.refresh(link)
    assert link.application_status == "OFFER"


def test_signature_hiring_gate_denies_without_contract_before_provisioning(db, monkeypatch):
    from app.domains.hiring.service import HiringConflictError
    job, candidate, link = _application(db)
    monkeypatch.setenv("ADN360_REQUIRE_SIGNED_CONTRACT_FOR_HIRE", "true")
    cognito = FakeCognito()
    with pytest.raises(HiringConflictError, match="Primero inicia la postulación"):
        _hire(db, cognito=cognito, job=job, candidate=candidate)
    assert cognito.created == []
    db.refresh(link)
    assert link.application_status == "OFFER"
    assert db.query(OdooEmployeeSync).count() == 0


def test_signature_gate_requires_verified_archived_file_before_hiring(db, monkeypatch):
    from datetime import datetime, timezone
    from app.domains.employee_documents.models import EmployeeDocument
    job, candidate, link = _application(db)
    applicant = UserProfile(cognito_sub="applicant-sign-test", email=candidate.email,
                            first_name="Ana", last_name="Pérez", status="ACTIVE",
                            login_username="ana.perez")
    db.add(applicant)
    db.flush()
    link.employee_id = applicant.id
    db.commit()
    contract = EmployeeDocument(
        employee_id=applicant.id, document_type="EMPLOYMENT_CONTRACT",
        review_status="APPROVED", odoo_sign_status="PREPARED",
        storage_key=f"training/employee-documents/{applicant.id}/original.pdf",
        odoo_sign_source_key=f"training/employee-documents/{applicant.id}/original.pdf",
        odoo_sign_request_id=139,
        odoo_sign_request_status="PARTIALLY_SIGNED",
        odoo_sign_employee_state="signed", odoo_sign_representative_state="sent",
    )
    db.add(contract)
    db.flush()
    from app.domains.employee_documents.models import ApplicationContract
    db.add(ApplicationContract(
        application_id=link.id, employee_id=applicant.id,
        document_id=contract.id, odoo_company_id=97,
        source_storage_key=contract.storage_key,
    ))
    db.commit()
    monkeypatch.setenv("ADN360_REQUIRE_SIGNED_CONTRACT_FOR_HIRE", "true")
    cognito = FakeCognito()
    with pytest.raises(hiring_service.HiringConflictError, match="ambas firmas"):
        _hire(db, cognito=cognito, job=job, candidate=candidate)
    assert cognito.created == []
    assert db.query(OdooEmployeeSync).count() == 0
    now = datetime.now(timezone.utc)
    contract.odoo_sign_request_status = "SIGNED"
    contract.odoo_sign_employee_state = "signed"
    contract.odoo_sign_representative_state = "signed"
    contract.odoo_sign_completed_at = now
    db.commit()
    with pytest.raises(hiring_service.HiringConflictError, match="archivar"):
        _hire(db, cognito=cognito, job=job, candidate=candidate)
    assert cognito.created == []
    contract.odoo_sign_signed_storage_key = (
        f"training/employee-documents/{applicant.id}/signed/139/test.pdf"
    )
    contract.odoo_sign_signed_sha256 = "a" * 64
    contract.odoo_sign_signed_at = now
    db.commit()
    readiness = hiring_service.hiring_signature_readiness(db, link=link)
    assert readiness["ready"] is True
    assert readiness["status"] == "SIGNED_CONTRACT_ARCHIVED"
    # A fully signed dossier is insufficient when the selected Odoo company
    # differs from the immutable company in the application binding.
    with pytest.raises(hiring_service.HiringValidationError, match="empresa Odoo"):
        _hire(db, cognito=cognito, job=job, candidate=candidate)
    assert cognito.created == []


def test_prepare_contract_dossier_creates_only_applicant_profile_without_login(db, monkeypatch):
    monkeypatch.setenv("ADN360_REQUIRE_SIGNED_CONTRACT_FOR_HIRE", "true")
    job, candidate, link = _application(db)
    first = hiring_service.prepare_candidate_contract_profile(
        db, owner_sub="admin-sub", job_id=job.id,
        candidate_id=candidate.id, created_by_sub="admin-sub",
    )
    assert first["employee_created"] is False
    assert first["access_provisioned"] is False
    profile = db.query(UserProfile).filter(UserProfile.id == first["profile_id"]).one()
    assert profile.cognito_sub is None
    assert profile.login_username is None
    assert profile.odoo_employee_id is None
    assert APPLICANT in employees_service.roles_for_profile(db, profile.id)
    assert EMPLOYEE not in employees_service.roles_for_profile(db, profile.id)
    assert db.query(OdooEmployeeSync).count() == 0
    second = hiring_service.prepare_candidate_contract_profile(
        db, owner_sub="admin-sub", job_id=job.id,
        candidate_id=candidate.id, created_by_sub="admin-sub",
    )
    assert second == first
    assert db.query(UserProfile).count() == 1


def test_prepare_dossier_disabled_until_signed_hiring_feature_is_enabled(db, monkeypatch):
    monkeypatch.delenv("ADN360_REQUIRE_SIGNED_CONTRACT_FOR_HIRE", raising=False)
    job, candidate, _ = _application(db)
    with pytest.raises(hiring_service.HiringConflictError, match="debe habilitarse"):
        hiring_service.prepare_candidate_contract_profile(
            db, owner_sub="admin-sub", job_id=job.id,
            candidate_id=candidate.id, created_by_sub="admin-sub",
        )
    assert db.query(UserProfile).count() == 0


def test_application_contract_binding_is_required_and_cannot_be_reused(db, monkeypatch):
    """A signed document for vacancy A never authorizes vacancy B."""
    from datetime import datetime, timezone
    from app.domains.employee_documents.models import ApplicationContract, EmployeeDocument

    monkeypatch.setenv("ADN360_REQUIRE_SIGNED_CONTRACT_FOR_HIRE", "true")
    job_a, candidate, link_a = _application(db)
    job_b = Job(
        title="Frontend Developer", description="React", owner_sub="admin-sub",
        country_code="CO", company_name="ASIATI Colombia", city="Bogotá",
    )
    db.add(job_b)
    db.flush()
    link_b = JobCandidate(
        job_id=job_b.id, candidate_id=candidate.id, application_status="OFFER",
    )
    db.add(link_b)
    profile = UserProfile(
        email=candidate.email, first_name="Ana", last_name="Pérez", status="ACTIVE",
    )
    db.add(profile)
    db.flush()
    link_a.employee_id = profile.id
    link_b.employee_id = profile.id
    now = datetime.now(timezone.utc)
    doc = EmployeeDocument(
        employee_id=profile.id, document_type="EMPLOYMENT_CONTRACT",
        review_status="APPROVED", storage_key="test/original.pdf",
        odoo_sign_source_key="test/original.pdf", odoo_sign_status="PREPARED",
        odoo_sign_request_id=140, odoo_sign_request_status="SIGNED",
        odoo_sign_employee_state="completed", odoo_sign_representative_state="completed",
        odoo_sign_completed_at=now, odoo_sign_signed_storage_key="test/signed.pdf",
        odoo_sign_signed_at=now, odoo_sign_signed_sha256="a" * 64,
    )
    db.add(doc)
    db.commit()

    # Legacy signed PDFs are preserved but cannot authorize an unbound application.
    assert hiring_service.hiring_signature_readiness(db, link=link_a)["status"] == (
        "APPLICATION_CONTRACT_BINDING_REQUIRED"
    )

    db.add(ApplicationContract(
        application_id=link_a.id, employee_id=profile.id,
        document_id=doc.id, odoo_company_id=97, source_storage_key=doc.storage_key,
    ))
    db.commit()
    assert hiring_service.hiring_signature_readiness(db, link=link_a)["status"] == (
        "SIGNED_CONTRACT_ARCHIVED"
    )
    assert hiring_service.hiring_signature_readiness(db, link=link_b)["status"] == (
        "APPLICATION_CONTRACT_BINDING_REQUIRED"
    )
    # Tampering with the source version must fail closed.
    doc.storage_key = "test/replaced.pdf"
    db.commit()
    assert hiring_service.hiring_signature_readiness(db, link=link_a)["ready"] is False


def test_application_contract_binding_happens_only_before_signing(db, monkeypatch):
    from app.domains.employee_documents.models import ApplicationContract, EmployeeDocument
    from app.domains.hiring import application_contracts as bindings

    monkeypatch.setenv("ADN360_APPLICATION_CONTRACT_BINDING_ENABLED", "true")
    monkeypatch.setattr(bindings.company_catalog, "require_company", lambda company_id: {"id": company_id, "name": "ASIATI"})
    job, candidate, link = _application(db)
    profile = UserProfile(
        email=candidate.email, first_name="Ana", last_name="Pérez", status="ACTIVE",
    )
    db.add(profile)
    db.flush()
    link.employee_id = profile.id
    doc = EmployeeDocument(
        employee_id=profile.id, document_type="EMPLOYMENT_CONTRACT",
        original_filename="contrato.pdf", content_type="application/pdf",
        review_status="APPROVED", storage_key="test/approved.pdf",
        odoo_sign_status="NOT_PREPARED", odoo_sign_request_status="UNLINKED",
    )
    db.add(doc)
    db.commit()

    first = bindings.bind(
        db, owner_sub="admin-sub", job_id=job.id, candidate_id=candidate.id,
        odoo_company_id=97,
    )
    assert first["bound"] and not first["already_bound"]
    repeat = bindings.bind(
        db, owner_sub="admin-sub", job_id=job.id, candidate_id=candidate.id,
        odoo_company_id=97,
    )
    assert repeat["already_bound"]
    assert db.query(ApplicationContract).count() == 1
    with pytest.raises(bindings.ContractBindingConflict, match="diferente"):
        bindings.bind(
            db, owner_sub="admin-sub", job_id=job.id, candidate_id=candidate.id,
            odoo_company_id=98,
        )

    # A different application for the same employee may not inherit the bound PDF.
    second_job = Job(title="QA", description="QA", owner_sub="admin-sub")
    db.add(second_job)
    db.flush()
    second_link = JobCandidate(
        job_id=second_job.id, candidate_id=candidate.id,
        employee_id=profile.id, application_status="SELECTED",
    )
    db.add(second_link)
    db.commit()
    with pytest.raises(bindings.ContractBindingConflict, match="otra postulación"):
        bindings.bind(
            db, owner_sub="admin-sub", job_id=second_job.id,
            candidate_id=candidate.id, odoo_company_id=97,
        )


def test_retroactive_binding_of_a_signed_legacy_contract_is_denied(db, monkeypatch):
    from app.domains.employee_documents.models import ApplicationContract, EmployeeDocument
    from app.domains.hiring import application_contracts as bindings

    monkeypatch.setenv("ADN360_APPLICATION_CONTRACT_BINDING_ENABLED", "true")
    job, candidate, link = _application(db)
    profile = UserProfile(email=candidate.email, status="ACTIVE")
    db.add(profile)
    db.flush()
    link.employee_id = profile.id
    db.add(EmployeeDocument(
        employee_id=profile.id, document_type="EMPLOYMENT_CONTRACT",
        original_filename="contrato-historico.pdf", content_type="application/pdf",
        review_status="APPROVED", storage_key="test/historical.pdf",
        odoo_sign_status="PREPARED", odoo_sign_request_id=140,
        odoo_sign_request_status="SIGNED",
    ))
    db.commit()
    with pytest.raises(bindings.ContractBindingConflict, match="retrospectivamente"):
        bindings.bind(
            db, owner_sub="admin-sub", job_id=job.id, candidate_id=candidate.id,
            odoo_company_id=97,
        )
    assert db.query(ApplicationContract).count() == 0
    assert db.query(EmployeeDocument).count() == 1


def test_hire_onboarding_failure_rolls_back_role_and_deletes_new_cognito_user(db, monkeypatch):
    """A failed onboarding cannot leave EMPLOYEE access or a Cognito orphan."""
    job, candidate, link = _application(db)

    class TrackedCognito(FakeCognito):
        def __init__(self):
            super().__init__()
            self.deleted = []

        def admin_delete_user(self, *, UserPoolId, Username):
            self.deleted.append(Username)

    cognito = TrackedCognito()

    def fail_after_role(*args, **kwargs):
        raise training_service.TrainingStateError("simulated onboarding failure")

    monkeypatch.setattr(
        training_service, "ensure_employee_asiati_onboarding", fail_after_role,
    )

    with pytest.raises(training_service.TrainingStateError, match="simulated onboarding"):
        _hire(db, cognito=cognito, job=job, candidate=candidate)

    db.expire_all()
    link = db.query(JobCandidate).filter(JobCandidate.id == link.id).one()
    assert link.application_status == "OFFER"
    assert link.employee_id is None
    assert link.hired_at is None
    assert db.query(UserProfile).count() == 0
    assert db.query(TrainingAssignment).count() == 0
    assert db.query(OdooApplicantSync).count() == 0
    assert db.query(OdooEmployeeSync).count() == 0
    assert cognito.created == ["ana@example.com"]
    assert cognito.deleted == ["ana@example.com"]


def test_hire_late_outbox_failure_does_not_promote_existing_applicant(db, monkeypatch):
    """A DB failure after onboarding leaves an existing portal applicant untouched."""
    job, candidate, link = _application(db)
    applicant = UserProfile(
        cognito_sub="sub-existing-applicant",
        email="ana@example.com",
        login_username="ana.perez",
        first_name="Ana",
        last_name="Pérez",
        onboarding_status="NOT_REQUIRED",
        status="ACTIVE",
    )
    db.add(applicant)
    db.flush()
    assign_role(db, applicant, APPLICANT, assigned_by_sub="test")
    link.employee_id = applicant.id
    db.commit()

    def fail_outbox(*args, **kwargs):
        raise RuntimeError("simulated outbox failure")

    monkeypatch.setattr(
        hiring_service.odoo_sync_service, "ensure_employee_sync", fail_outbox,
    )

    with pytest.raises(RuntimeError, match="simulated outbox failure"):
        _hire(db, cognito=FakeCognito(), job=job, candidate=candidate)

    db.expire_all()
    link = db.query(JobCandidate).filter(JobCandidate.id == link.id).one()
    profile = db.query(UserProfile).filter(UserProfile.id == applicant.id).one()
    assert link.application_status == "OFFER"
    assert link.hired_at is None
    assert profile.onboarding_status == "NOT_REQUIRED"
    assert employees_service.roles_for_profile(db, profile.id) == [APPLICANT]
    assert db.query(TrainingAssignment).count() == 0
    assert db.query(OdooApplicantSync).count() == 0
    assert db.query(OdooEmployeeSync).count() == 0


def test_hire_outbox_failure_compensates_new_cognito_user(db, monkeypatch):
    """A failure at the final transaction stage also compensates Cognito."""
    job, candidate, link = _application(db)

    class TrackedCognito(FakeCognito):
        def __init__(self):
            super().__init__()
            self.deleted = []

        def admin_delete_user(self, *, UserPoolId, Username):
            self.deleted.append(Username)

    cognito = TrackedCognito()

    def fail_outbox(*args, **kwargs):
        raise RuntimeError("outbox unavailable")

    monkeypatch.setattr(
        hiring_service.odoo_sync_service, "ensure_employee_sync", fail_outbox,
    )

    with pytest.raises(RuntimeError, match="outbox unavailable"):
        _hire(db, cognito=cognito, job=job, candidate=candidate)

    db.expire_all()
    assert db.query(UserProfile).count() == 0
    assert db.query(TrainingAssignment).count() == 0
    assert db.query(JobCandidate).filter(JobCandidate.id == link.id).one().application_status == "OFFER"
    assert cognito.deleted == ["ana@example.com"]
