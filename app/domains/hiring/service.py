"""Orchestration from a hired application to employee onboarding."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.access_control import EMPLOYEE, assign_role, normalize_email
from app.domains.candidates import repository as candidates_repository
from app.domains.candidates import service as candidates_service
from app.domains.employees import service as employees_service
from app.domains.indeed import service as indeed_service
from app.domains.training import service as training_service
from app.models import UserProfile


class HiringValidationError(ValueError):
    pass


class HiringConflictError(RuntimeError):
    pass


def _employee_names(
    candidate_name: str | None,
    *,
    first_name: str | None,
    last_name: str | None,
) -> tuple[str, str]:
    resolved_first = str(first_name or "").strip()
    resolved_last = str(last_name or "").strip()
    parts = str(candidate_name or "").strip().split()

    if not resolved_first and parts:
        resolved_first = parts[0]
    if not resolved_last and len(parts) > 1:
        resolved_last = " ".join(parts[1:])

    if not resolved_first or not resolved_last:
        raise HiringValidationError(
            "Confirma nombre y apellido antes de contratar al candidato."
        )
    return resolved_first, resolved_last


def _ensure_employee_role(
    db: Session,
    employee: UserProfile,
    *,
    assigned_by_sub: str,
) -> None:
    if employees_service.roles_for_profile(db, employee.id):
        return
    assign_role(
        db,
        employee,
        EMPLOYEE,
        assigned_by_sub=assigned_by_sub,
    )
    db.commit()


def hire_candidate(
    db: Session,
    *,
    owner_sub: str,
    job_id: str,
    candidate_id: str,
    created_by_sub: str,
    email: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    job_title: str | None = None,
    department: str | None = None,
    hire_date: date | None = None,
    cognito_client=None,
) -> dict:
    job = candidates_service.require_job(db, job_id, owner_sub)
    candidate = candidates_service.require_candidate(db, candidate_id, owner_sub)
    link = candidates_repository.get_job_candidate(
        db,
        job_id=job_id,
        candidate_id=candidate_id,
        owner_sub=owner_sub,
    )
    if link is None:
        raise candidates_service.JobCandidateNotFound(candidate_id)
    if candidate.is_banned:
        raise HiringConflictError("No puedes contratar un candidato vetado.")

    resolved_email = normalize_email(email or candidate.email or "")
    if not resolved_email:
        raise HiringValidationError(
            "El candidato necesita un correo antes de crear su acceso."
        )

    resolved_first, resolved_last = _employee_names(
        candidate.name,
        first_name=first_name,
        last_name=last_name,
    )
    resolved_job_title = str(job_title or job.title or "").strip() or None
    resolved_department = str(department or "").strip() or None
    resolved_hire_date = hire_date or date.today()

    employee = (
        db.query(UserProfile)
        .filter(UserProfile.email == resolved_email)
        .one_or_none()
    )
    employee_created = False

    if employee is None:
        try:
            employee = employees_service.create_employee(
                db,
                email=resolved_email,
                first_name=resolved_first,
                last_name=resolved_last,
                job_title=resolved_job_title,
                department=resolved_department,
                hire_date=resolved_hire_date,
                role_code=EMPLOYEE,
                created_by_sub=created_by_sub,
                cognito_client=cognito_client,
            )
            employee_created = True
        except employees_service.EmployeeAlreadyExists:
            employee = (
                db.query(UserProfile)
                .filter(UserProfile.email == resolved_email)
                .one_or_none()
            )
            if employee is None:
                raise
    else:
        if employee.status != "ACTIVE":
            raise HiringConflictError(
                "Ya existe un usuario deshabilitado con este correo."
            )
        changed = False
        for field, value in {
            "first_name": resolved_first,
            "last_name": resolved_last,
            "job_title": resolved_job_title,
            "department": resolved_department,
            "hire_date": resolved_hire_date,
        }.items():
            if value is not None and not getattr(employee, field):
                setattr(employee, field, value)
                changed = True
        if changed:
            db.commit()
            db.refresh(employee)
        _ensure_employee_role(
            db,
            employee,
            assigned_by_sub=created_by_sub,
        )

    course = training_service.ensure_published_asiati_onboarding(
        db,
        created_by_sub=created_by_sub,
    )
    assignment = training_service.assign_course(
        db,
        course_id=course.id,
        employee_id=employee.id,
        assigned_by_sub=created_by_sub,
    )

    link.employee_id = employee.id
    if link.hired_at is None:
        link.hired_at = datetime.now(timezone.utc)

    status_changed = link.application_status != "HIRED"
    if status_changed:
        candidates_repository.set_job_candidate_status(
            db,
            link,
            status="HIRED",
        )
        indeed_service.queue_candidate_status(
            db,
            owner_sub=owner_sub,
            job_id=job_id,
            candidate_id=candidate_id,
            local_status="HIRED",
            status_changed_at=link.status_changed_at,
        )

    db.commit()
    db.refresh(link)
    db.refresh(employee)
    db.refresh(assignment)

    return {
        "job_id": job_id,
        "candidate_id": candidate_id,
        "application_status": link.application_status,
        "status_changed": status_changed,
        "hired_at": link.hired_at.isoformat() if link.hired_at else None,
        "employee_created": employee_created,
        "employee": employees_service.employee_payload(db, employee),
        "onboarding_assignment": training_service.assignment_payload(db, assignment),
    }
