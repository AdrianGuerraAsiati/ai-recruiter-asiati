"""Starting an application from global ranking must not hire the person."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.access_control import APPLICANT, ensure_rbac_catalog, resolve_principal
from app.db import Base
from app.domains.hiring import service
from app.domains.employees.service import roles_for_profile
from app.domains.indeed import service as indeed_service
from app.models import Candidate, Job, JobCandidate, UserProfile


class FakeCognito:
    def admin_create_user(self, **kwargs):
        email = kwargs["Username"]
        return {"User": {"Attributes": [{"Name": "sub", "Value": f"sub-{email}"}]}}

    def admin_delete_user(self, **_kwargs):
        raise AssertionError("The newly-created account must not be deleted")


@pytest.fixture()
def context(monkeypatch):
    monkeypatch.setenv("COGNITO_USER_POOL_ID", "pool-e2e")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    ensure_rbac_catalog(db)
    db.add(Job(id="10000000-0000-0000-0000-000000000a01", title="Desarrollador", status="ACTIVE", country_code="CO"))
    db.add(Job(id="20000000-0000-0000-0000-000000000b02", title="Analista", status="ACTIVE", country_code="CO"))
    db.add(Candidate(id="30000000-0000-0000-0000-000000000c03", name="Ana Pérez", email="ana@example.com"))
    db.commit()
    monkeypatch.setattr(indeed_service, "queue_candidate_status", lambda *args, **kwargs: None)
    yield db
    db.close()
    engine.dispose()


def start(db, job_id="10000000-0000-0000-0000-000000000a01"):
    return service.start_candidate_application(
        db,
        owner_sub="admin-sub",
        job_id=job_id,
        candidate_id="30000000-0000-0000-0000-000000000c03",
        created_by_sub="admin-sub",
        username="aperez",
        cognito_client=FakeCognito(),
    )


def test_selected_application_provisions_once_without_hiring(context):
    assert context.query(JobCandidate).count() == 0

    first = start(context)
    link = context.query(JobCandidate).one()
    employee = context.query(UserProfile).one()
    assert first["employee_created"] is False
    assert first["applicant_access_created"] is True
    assert first["credentials"]["must_change_password"] is True
    assert first["credentials"]["username"] == "aperez"
    assert len(first["credentials"]["temporary_password"]) >= 12
    assert first["application_status"] == "SELECTED"
    assert link.employee_id == employee.id
    assert link.hired_at is None
    assert employee.hire_date is None
    assert employee.onboarding_status == "NOT_REQUIRED"
    assert roles_for_profile(context, employee.id) == [APPLICANT]
    # Login must never bootstrap a document-only applicant into EMPLOYEE.
    principal = resolve_principal(context, {"sub": employee.cognito_sub, "email": employee.email})
    assert principal["roles"] == [APPLICANT]
    assert set(principal["permissions"]) == {
        "profile.read_own", "employee_documents.read_own", "employee_documents.upload_own",
    }

    repeat = start(context)
    assert repeat["already_started"] is True
    assert repeat["credentials"] is None
    assert context.query(JobCandidate).count() == 1
    assert context.query(UserProfile).count() == 1

    another_vacancy = start(context, "20000000-0000-0000-0000-000000000b02")
    assert another_vacancy["employee_created"] is False
    assert another_vacancy["credentials"] is None
    assert context.query(JobCandidate).count() == 2
    assert context.query(UserProfile).count() == 1


def test_banned_candidate_is_not_linked_or_provisioned(context):
    candidate = context.query(Candidate).one()
    candidate.is_banned = True
    context.commit()
    with pytest.raises(service.HiringConflictError, match="vetado"):
        start(context)
    assert context.query(JobCandidate).count() == 0
    assert context.query(UserProfile).count() == 0


def test_paused_job_cannot_start_application(context):
    job = context.query(Job).filter(Job.id == "10000000-0000-0000-0000-000000000a01").one()
    job.status = "PAUSED"
    context.commit()
    with pytest.raises(service.HiringConflictError, match="activas"):
        start(context)
    assert context.query(JobCandidate).count() == 0
