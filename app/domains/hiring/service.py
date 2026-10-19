"""Orchestration from a hired application to employee onboarding."""

from __future__ import annotations

import os
import re
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.access_control import ADMIN, APPLICANT, EMPLOYEE, assign_role, normalize_email
from app.domains.candidates import repository as candidates_repository
from app.domains.candidates import service as candidates_service
from app.domains.employees import service as employees_service
from app.domains.employee_documents import notifications as document_notifications
from app.domains.employee_documents.models import EmployeeDocument
from app.domains.indeed import service as indeed_service
from app.domains.odoo_sync import company_catalog
from app.domains.odoo_sync import contract_delivery
from app.domains.odoo_sync import employee_delivery
from app.domains.odoo_sync import integration as odoo_integration
from app.domains.odoo_sync import service as odoo_sync_service
from app.domains.training import service as training_service
from app.domains.psychotechnical import service as psychotechnical_service
from app.models import UserProfile, UserRole


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
    roles = employees_service.roles_for_profile(db, employee.id)
    if EMPLOYEE in roles or ADMIN in roles:
        return
    if APPLICANT in roles:
        db.query(UserRole).filter(
            UserRole.user_id == employee.id,
            UserRole.role_code == APPLICANT,
        ).delete(synchronize_session=False)
        db.flush()
    assign_role(
        db,
        employee,
        EMPLOYEE,
        assigned_by_sub=assigned_by_sub,
    )
    db.commit()


def start_candidate_application(
    db: Session,
    *,
    owner_sub: str,
    job_id: str,
    candidate_id: str,
    created_by_sub: str,
    username: str,
    email: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    department: str | None = None,
    cognito_client=None,
) -> dict:
    """Start a selected application and provision portal access without hiring.

    Rankings evaluate the whole candidate pool, so the JobCandidate relation is
    created only when an administrator initiates the application. Retrying this
    action must not generate another password or employee identity.
    """
    job = candidates_service.require_job(db, job_id, owner_sub)
    candidate = candidates_service.require_candidate(db, candidate_id, owner_sub)
    if candidate.is_banned:
        raise HiringConflictError("No puedes iniciar la postulación de un candidato vetado.")
    if str(job.status or "").upper() != "ACTIVE":
        raise HiringConflictError("Solo puedes iniciar postulaciones en vacantes activas.")

    resolved_email = normalize_email(email or candidate.email or "")
    if not resolved_email:
        raise HiringValidationError("El candidato necesita un correo para recibir acceso.")
    resolved_username = employees_service.normalize_login_username(username)
    resolved_first, resolved_last = _employee_names(
        candidate.name, first_name=first_name, last_name=last_name
    )
    link = candidates_repository.get_job_candidate(
        db, job_id=job_id, candidate_id=candidate_id, owner_sub=None
    )
    if link is not None and link.application_status in {"HIRED", "WITHDRAWN", "REJECTED"}:
        raise HiringConflictError(
            "Esta postulación ya fue cerrada. Revisa su estado antes de continuar."
        )
    if link is not None and link.employee_id:
        employee = employees_service.require_employee(db, link.employee_id)
        if normalize_email(employee.email) != resolved_email:
            raise HiringConflictError("El expediente está vinculado a otro correo. Revisa la identidad.")
        if employee.cognito_sub:
            psychotechnical_assignments = psychotechnical_service.ensure_hiring_assignments(
                db, candidate_id=candidate_id, job_id=job_id,
                created_by_sub=created_by_sub,
            )
            return {
            "job_id": job_id,
            "candidate_id": candidate_id,
            "application_id": link.id,
            "application_status": link.application_status,
            "employee_created": False,
            "employee": employees_service.employee_payload(db, employee),
            "credentials": None,
            "already_started": True,
            "psychotechnical_assignments": psychotechnical_assignments,
            }

    employee = (
        db.query(UserProfile)
        .filter(UserProfile.email == resolved_email)
        .one_or_none()
    )
    employee_created = False
    temporary_password = None
    if employee is not None:
        if employee.status != "ACTIVE":
            raise HiringConflictError("El usuario existente se encuentra deshabilitado.")
        # Imported Odoo profiles can exist without an authentication identity.
        if employee.login_username and employee.login_username != resolved_username:
            raise HiringConflictError(
                "El correo ya tiene otro usuario. Consulta o edita sus credenciales en Empleados."
            )

    # The assignment is flushed with the employee provisioning transaction.
    link = link or candidates_repository.ensure_candidate_assigned_to_job(
        db, job_id=job_id, candidate_id=candidate_id
    )
    if employee is None:
        try:
            employee, temporary_password = employees_service.provision_employee(
                db,
                username=resolved_username,
                email=resolved_email,
                first_name=resolved_first,
                last_name=resolved_last,
                job_title=str(job.title or "").strip() or None,
                department=str(department or "").strip() or None,
                country_code=str(getattr(job, "country_code", None) or "").strip() or None,
                company_name=str(getattr(job, "company_name", None) or "").strip() or None,
                # Hiring date and Odoo employee creation are reserved for /hire.
                hire_date=None,
                role_code=APPLICANT,
                created_by_sub=created_by_sub,
                cognito_client=cognito_client,
            )
            employee_created = False
        except Exception:
            db.rollback()
            raise
    elif not employee.cognito_sub:
        employee, temporary_password = employees_service.provision_existing_profile_access(
            db,
            employee.id,
            username=resolved_username,
            first_name=resolved_first,
            last_name=resolved_last,
            role_code=APPLICANT,
            created_by_sub=created_by_sub,
            cognito_client=cognito_client,
        )
    elif not employee.login_username:
        employee = employees_service.set_employee_username(
            db, employee.id, username=resolved_username
        )

    # A recruiter may issue document-access credentials without hiring.
    # Promotion to EMPLOYEE occurs only inside hire_candidate().
    link.employee_id = employee.id
    if link.application_status != "SELECTED":
        candidates_repository.set_job_candidate_status(db, link, status="SELECTED")
        indeed_service.queue_candidate_status(
            db,
            owner_sub=owner_sub,
            job_id=job_id,
            candidate_id=candidate_id,
            local_status="SELECTED",
            status_changed_at=link.status_changed_at,
        )
    db.commit()
    db.refresh(link)
    psychotechnical_assignments = psychotechnical_service.ensure_hiring_assignments(
        db, candidate_id=candidate_id, job_id=job_id,
        created_by_sub=created_by_sub,
    )

    return {
        "job_id": job_id,
        "candidate_id": candidate_id,
        "application_id": link.id,
        "application_status": link.application_status,
        "employee_created": False,
        "applicant_access_created": bool(temporary_password),
        "employee": employees_service.employee_payload(db, employee),
        "credentials": (
            {
                "username": employee.login_username,
                "temporary_password": temporary_password,
                "must_change_password": True,
            }
            if temporary_password
            else None
        ),
        "already_started": False,
        "psychotechnical_assignments": psychotechnical_assignments,
    }


def prepare_candidate_contract_profile(
    db: Session,
    *,
    owner_sub: str,
    job_id: str,
    candidate_id: str,
    created_by_sub: str,
) -> dict:
    """Associate a candidate with a pre-hire document dossier, WITHOUT Cognito.

    The profile uses the APPLICANT role and remains hidden from the Employee
    directory. The person is not hired and no Odoo employee is created.
    """
    if not signed_contract_hiring_gate_enabled():
        raise HiringConflictError(
            "El nuevo flujo de contratos debe habilitarse tras las pruebas de firma."
        )
    job = candidates_service.require_job(db, job_id, owner_sub)
    candidate = candidates_service.require_candidate(db, candidate_id, owner_sub)
    link = candidates_repository.get_job_candidate(
        db, job_id=job_id, candidate_id=candidate_id, owner_sub=None,
    )
    if link is None:
        raise candidates_service.JobCandidateNotFound(candidate_id)
    if candidate.is_banned or link.application_status in {"HIRED", "WITHDRAWN", "REJECTED"}:
        raise HiringConflictError("No se puede preparar contrato para una postulación cerrada o vetada.")
    if link.employee_id:
        profile = employees_service.require_employee(db, link.employee_id)
        return {
            "profile_id": profile.id,
            "employee_created": False,
            "access_provisioned": bool(profile.cognito_sub),
        }
    email = normalize_email(candidate.email or "")
    if not email:
        raise HiringValidationError("El candidato necesita correo para solicitar firmas.")
    existing = db.query(UserProfile).filter(UserProfile.email == email).one_or_none()
    if existing is not None:
        roles = employees_service.roles_for_profile(db, existing.id)
        if EMPLOYEE in roles or ADMIN in roles or existing.odoo_employee_id:
            raise HiringConflictError("Este correo ya pertenece a un empleado; revisa el expediente.")
        profile = existing
    else:
        first, last = _employee_names(candidate.name, first_name=None, last_name=None)
        profile = UserProfile(
            email=email, first_name=first, last_name=last,
            job_title=str(job.title or "").strip() or None,
            country_code=str(job.country_code or "").strip() or None,
            company_name=str(job.company_name or "").strip() or None,
            created_by_sub=created_by_sub,
            status="ACTIVE",
            onboarding_status="NOT_REQUIRED",
        )
        db.add(profile)
        db.flush()
    roles = employees_service.roles_for_profile(db, profile.id)
    if APPLICANT not in roles:
        assign_role(db, profile, APPLICANT, assigned_by_sub=created_by_sub)
    link.employee_id = profile.id
    db.commit()
    return {
        "profile_id": profile.id,
        "employee_created": False,
        "access_provisioned": bool(profile.cognito_sub),
    }


def signed_contract_hiring_gate_enabled() -> bool:
    """Enable after Odoo Sign production workflow + archival E2E is validated."""
    return os.getenv("ADN360_REQUIRE_SIGNED_CONTRACT_FOR_HIRE", "").strip().lower() in (
        "1", "true", "yes"
    )


def hiring_signature_readiness(db: Session, *, link) -> dict:
    """Read-only gate: do not create a Cognito account or Odoo employee here."""
    enabled = signed_contract_hiring_gate_enabled()
    if not enabled:
        return {"enabled": False, "ready": True, "status": "LEGACY_FLOW",
                "message": "El bloqueo por firma se habilitará después de las pruebas."}
    if link.application_status == "HIRED":
        return {"enabled": True, "ready": True, "status": "ALREADY_HIRED",
                "message": "La postulación ya está contratada."}
    if not link.employee_id:
        return {"enabled": True, "ready": False, "status": "APPLICANT_PROFILE_REQUIRED",
                "message": "Primero inicia la postulación y crea el perfil del postulante."}
    document = db.query(EmployeeDocument).filter(
        EmployeeDocument.employee_id == link.employee_id,
        EmployeeDocument.document_type == "EMPLOYMENT_CONTRACT",
    ).one_or_none()
    if (
        document is None
        or document.review_status != "APPROVED"
        or document.odoo_sign_status != "PREPARED"
        or document.odoo_sign_source_key != document.storage_key
        or document.odoo_sign_request_id is None
        or document.odoo_sign_request_status != "SIGNED"
        or document.odoo_sign_employee_state not in ("signed", "completed")
        or document.odoo_sign_representative_state not in ("signed", "completed")
        or not document.odoo_sign_completed_at
        or not document.odoo_sign_signed_storage_key
        or not document.odoo_sign_signed_at
        or not re.fullmatch(r"[0-9a-f]{64}", document.odoo_sign_signed_sha256 or "")
    ):
        return {"enabled": True, "ready": False, "status": "CONTRACT_SIGNATURE_PENDING",
                "message": "Debes obtener ambas firmas y archivar el PDF final antes de crear el empleado."}
    return {"enabled": True, "ready": True, "status": "SIGNED_CONTRACT_ARCHIVED",
            "message": "Ambas firmas verificadas y contrato firmado archivado. Puedes contratar."}


def hire_candidate(
    db: Session,
    *,
    owner_sub: str,
    job_id: str,
    candidate_id: str,
    created_by_sub: str,
    username: str,
    email: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    job_title: str | None = None,
    department: str | None = None,
    country_code: str | None = None,
    company_name: str | None = None,
    odoo_company_id: int | None = None,
    hire_date: date | None = None,
    contract: dict | None = None,
    cognito_client=None,
) -> dict:
    job = candidates_service.require_job(db, job_id, owner_sub)
    candidate = candidates_service.require_candidate(db, candidate_id, owner_sub)
    link = candidates_repository.get_job_candidate(
        db,
        job_id=job_id,
        candidate_id=candidate_id,
        owner_sub=None,
    )
    if link is None:
        raise candidates_service.JobCandidateNotFound(candidate_id)
    if candidate.is_banned:
        raise HiringConflictError("No puedes contratar un candidato vetado.")

    # Deliberately before ANY Cognito, employee-role, Odoo or onboarding writes.
    # Applicant login (if already present) remains an APPLICANT until this passes.
    signature_gate = hiring_signature_readiness(db, link=link)
    if not signature_gate["ready"]:
        raise HiringConflictError(signature_gate["message"])

    resolved_username = employees_service.normalize_login_username(username)
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
    resolved_country_code = str(country_code or getattr(job, "country_code", None) or "").strip().upper() or None
    # Resolve company from Odoo before any employee, Cognito, or outbox writes.
    # For legacy calls, the existing company name remains supported until the
    # signature-first flow is enabled in production.
    if odoo_company_id is not None:
        try:
            selected_company = company_catalog.require_company(odoo_company_id)
        except company_catalog.OdooCompanyNotFound as exc:
            raise HiringValidationError(str(exc)) from exc
        except (odoo_integration.OdooDisabled, odoo_integration.OdooNotConfigured):
            raise HiringConflictError("No está disponible el catálogo de empresas de Odoo.") from None
        resolved_company_name = selected_company["name"]
    elif signed_contract_hiring_gate_enabled():
        raise HiringValidationError("Debes seleccionar una empresa activa de Odoo antes de contratar.")
    else:
        resolved_company_name = str(company_name or getattr(job, "company_name", None) or "").strip() or None
    resolved_hire_date = hire_date or date.today()

    if link.employee_id:
        employee = employees_service.require_employee(db, link.employee_id)
        if normalize_email(employee.email) != resolved_email:
            raise HiringConflictError(
                "No puedes cambiar la identidad del postulante durante la contratación."
            )
    else:
        employee = (
            db.query(UserProfile)
            .filter(UserProfile.email == resolved_email)
            .one_or_none()
        )
    employee_created = False
    temporary_password = None

    if employee is None:
        try:
            employee, temporary_password = employees_service.provision_employee(
                db,
                username=resolved_username,
                email=resolved_email,
                first_name=resolved_first,
                last_name=resolved_last,
                job_title=resolved_job_title,
                department=resolved_department,
                country_code=resolved_country_code,
                company_name=resolved_company_name,
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
                employee = employees_service.ensure_existing_cognito_profile(
                    db,
                    email=resolved_email,
                    created_by_sub=created_by_sub,
                    cognito_client=cognito_client,
                )
    if employee.status != "ACTIVE":
        raise HiringConflictError(
            "Ya existe un usuario deshabilitado con este correo."
        )

    # A pre-contract profile deliberately has no Cognito identity.
    # Provision access only AFTER the signed-contract gate succeeds.
    if not employee.cognito_sub:
        employee, temporary_password = employees_service.provision_existing_profile_access(
            db,
            employee.id,
            username=resolved_username,
            first_name=resolved_first,
            last_name=resolved_last,
            role_code=EMPLOYEE,
            created_by_sub=created_by_sub,
            cognito_client=cognito_client,
        )

    if employee.login_username and employee.login_username != resolved_username:
        raise HiringConflictError(
            f"El empleado existente ya usa el usuario {employee.login_username}."
        )
    if not employee.login_username:
        employee = employees_service.set_employee_username(
            db,
            employee.id,
            username=resolved_username,
        )

    changed = False
    for field, value in {
        "first_name": resolved_first,
        "last_name": resolved_last,
        "job_title": resolved_job_title,
        "department": resolved_department,
        "country_code": resolved_country_code,
        "company_name": resolved_company_name,
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

    if employee.onboarding_status == "NOT_REQUIRED":
        employee.onboarding_status = "PENDING"
        db.commit()
        db.refresh(employee)

    assignment = training_service.ensure_employee_asiati_onboarding(
        db,
        employee_id=employee.id,
        created_by_sub=created_by_sub,
    )
    if assignment is None:
        raise HiringConflictError(
            "El empleado contratado no es elegible para el onboarding automático."
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

    applicant_sync = odoo_sync_service.ensure_applicant_sync(
        db,
        candidate=candidate,
        job=job,
        application=link,
    )
    odoo_sync = odoo_sync_service.ensure_employee_sync(
        db,
        employee=employee,
        candidate=candidate,
        job=job,
        application=link,
    )
    contract_sync = None
    if contract is not None:
        contract_sync = odoo_sync_service.ensure_contract_sync(
            db,
            employee=employee,
            job=job,
            application=link,
            contract=contract,
        )

    db.commit()
    db.refresh(link)
    db.refresh(employee)
    db.refresh(assignment)

    odoo_delivery = None
    try:
        odoo_delivery = employee_delivery.sync_employee_now(
            db, employee_id=employee.id
        )
    except (
        employee_delivery.OdooEmployeeDeliveryError,
        employee_delivery.OdooEmployeeSyncNotFound,
        odoo_integration.OdooDisabled,
        odoo_integration.OdooNotConfigured,
    ):
        pass
    db.refresh(odoo_sync)

    odoo_contract_delivery = None
    if contract_sync is not None:
        try:
            if odoo_sync.odoo_record_id:
                odoo_contract_delivery = contract_delivery.sync_contract_now(
                    db,
                    employee_id=employee.id,
                )
        except (
            contract_delivery.OdooContractDeliveryError,
            contract_delivery.OdooContractSyncNotFound,
            contract_delivery.OdooContractDependencyError,
            odoo_integration.OdooDisabled,
            odoo_integration.OdooNotConfigured,
        ):
            pass
        db.refresh(contract_sync)

    # Welcome/document request email is sent only after the formal hire has
    # committed. Repeated hiring attempts never re-send a delivered message.
    # SES failures must not roll back an already-hired employee.
    welcome_email = {"status": "NOT_REQUESTED", "attempt_count": 0, "sent_at": None}
    if status_changed:
        try:
            welcome_email = document_notifications.send_welcome(db, employee.id)
        except Exception:
            # An email integration outage must not invalidate a committed hire.
            welcome_email = {"status": "FAILED", "reason": "WELCOME_EMAIL_UNAVAILABLE"}
    else:
        welcome_email = document_notifications.status_for_employee(db, employee.id)

    return {
        "job_id": job_id,
        "candidate_id": candidate_id,
        "application_status": link.application_status,
        "status_changed": status_changed,
        "welcome_email": welcome_email,
        "hired_at": link.hired_at.isoformat() if link.hired_at else None,
        "employee_created": employee_created,
        "employee": employees_service.employee_payload(db, employee),
        "credentials": (
            {
                "username": employee.login_username,
                "temporary_password": temporary_password,
                "must_change_password": True,
            }
            if temporary_password
            else None
        ),
        "onboarding_assignment": training_service.assignment_payload(db, assignment),
        "odoo_applicant_sync": odoo_sync_service.applicant_sync_payload(applicant_sync),
        "odoo_sync": odoo_sync_service.sync_payload(odoo_sync),
        "odoo_delivery": odoo_delivery,
        "odoo_contract_sync": (
            odoo_sync_service.contract_sync_payload(contract_sync)
            if contract_sync is not None
            else None
        ),
        "odoo_contract_delivery": odoo_contract_delivery,
    }
