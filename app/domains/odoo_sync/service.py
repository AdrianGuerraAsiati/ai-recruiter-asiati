"""Durable Odoo employee synchronization outbox.

This module deliberately prepares and persists the synchronization contract without
performing network I/O. Transport to Odoo is a separate concern so hiring remains
successful even when Odoo is unavailable.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import (
    Candidate,
    Job,
    JobCandidate,
    OdooApplicantSync,
    OdooEmployeeSync,
    OdooJobSync,
    UserProfile,
)


SYNC_PENDING = "PENDING"
SYNC_SYNCED = "SYNCED"
SYNC_FAILED = "FAILED"

ODOO_RECRUITMENT_STAGE_BY_STATUS = {
    "APPLIED": "New",
    "SCREENING": "Initial Qualification",
    "INITIAL_QUALIFICATION": "Initial Qualification",
    "INTERVIEW": "First Interview",
    "FIRST_INTERVIEW": "First Interview",
    "SECOND_INTERVIEW": "Second Interview",
    "SELECTED": "Contract Proposal",
    "OFFER": "Contract Proposal",
    "CONTRACT_PROPOSAL": "Contract Proposal",
    "CONTRACT_SIGNED": "Contract Signed",
    "HIRED": "Contract Signed",
}


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _candidate_phone(candidate: Candidate) -> str | None:
    metadata = candidate.metadata_ or {}
    sources = [metadata]
    contact = metadata.get("contact")
    if isinstance(contact, dict):
        sources.append(contact)
    for source in sources:
        for key in ("phone", "phone_number", "mobile", "mobile_phone", "telefono", "teléfono"):
            value = str(source.get(key) or "").strip()
            if value:
                return value
    return None


def build_job_upsert_payload(*, job: Job) -> dict:
    """Build the versioned contract used to mirror one Talent vacancy to Odoo."""

    return {
        "schema_version": 1,
        "operation": "UPSERT_JOB",
        "job": {
            "external_id": job.id,
            "title": job.title,
            "description": job.description,
            "status": getattr(job, "status", None) or "ACTIVE",
            "country_code": getattr(job, "country_code", None),
            "city": getattr(job, "city", None),
            "employment_type": getattr(job, "employment_type", None),
            "public_slug": getattr(job, "public_slug", None),
            "published_at": _iso(getattr(job, "published_at", None)),
        },
    }


def ensure_job_sync(db: Session, *, job: Job) -> OdooJobSync:
    """Create or refresh the durable Odoo mirror state for one Talent vacancy."""

    payload = build_job_upsert_payload(job=job)
    sync = (
        db.query(OdooJobSync)
        .filter(OdooJobSync.job_id == job.id)
        .one_or_none()
    )
    if sync is None:
        sync = OdooJobSync(
            job_id=job.id,
            idempotency_key=f"job:{job.id}",
            payload=payload,
            status=SYNC_PENDING,
        )
        db.add(sync)
        db.flush()
        return sync

    payload_changed = sync.payload != payload
    sync.payload = payload
    if payload_changed:
        sync.status = SYNC_PENDING
        sync.last_error = None
        sync.synced_at = None
    db.flush()
    return sync


def job_sync_payload(sync: OdooJobSync) -> dict:
    return {
        "id": sync.id,
        "job_id": sync.job_id,
        "idempotency_key": sync.idempotency_key,
        "status": sync.status,
        "attempt_count": sync.attempt_count,
        "odoo_record_id": sync.odoo_record_id,
        "last_error": sync.last_error,
        "synced_at": _iso(sync.synced_at),
        "created_at": _iso(sync.created_at),
        "updated_at": _iso(sync.updated_at),
    }


def build_applicant_upsert_payload(
    *,
    candidate: Candidate,
    job: Job,
    application: JobCandidate,
) -> dict:
    """Build the selected-application contract consumed by the future Odoo transport."""

    return {
        "schema_version": 1,
        "operation": "UPSERT_APPLICANT",
        "source": {
            "candidate_id": candidate.id,
            "job_id": job.id,
            "application_id": application.id,
            "application_status": application.application_status,
            "odoo_stage_name": ODOO_RECRUITMENT_STAGE_BY_STATUS.get(application.application_status),
            "status_changed_at": _iso(application.status_changed_at),
        },
        "candidate": {
            "external_id": candidate.id,
            "name": candidate.name,
            "email": candidate.email,
            "phone": _candidate_phone(candidate),
        },
        "documents": {
            "candidate_cv": {
                "candidate_id": candidate.id,
                "source": "CANONICAL_CANDIDATE_DOCUMENT",
            }
        },
        "job": {
            "external_id": job.id,
            "title": job.title,
            "country_code": job.country_code,
            "city": job.city,
            "employment_type": job.employment_type,
            "selection_process": {
                "response_time_business_days": getattr(
                    job, "response_time_business_days", 2
                ),
                "steps": [
                    {
                        "type": "PHONE_CALL",
                        "quantity": getattr(job, "phone_call_count", 1),
                    },
                    {
                        "type": "ONSITE_INTERVIEW",
                        "quantity": getattr(job, "onsite_interview_count", 1),
                    },
                ],
                "offer_wait_days": getattr(job, "offer_wait_days", 4),
                "offer_wait_reference": getattr(
                    job, "offer_wait_reference", "AFTER_INTERVIEW"
                ),
            },
        },
    }


def ensure_applicant_sync(
    db: Session,
    *,
    candidate: Candidate,
    job: Job,
    application: JobCandidate,
) -> OdooApplicantSync:
    """Create or refresh one idempotent Odoo applicant state per application."""

    payload = build_applicant_upsert_payload(
        candidate=candidate,
        job=job,
        application=application,
    )
    sync = (
        db.query(OdooApplicantSync)
        .filter(OdooApplicantSync.job_candidate_id == application.id)
        .one_or_none()
    )
    if sync is None:
        sync = OdooApplicantSync(
            job_candidate_id=application.id,
            idempotency_key=f"application:{application.id}",
            payload=payload,
            status=SYNC_PENDING,
        )
        db.add(sync)
        db.flush()
        return sync

    payload_changed = sync.payload != payload
    sync.payload = payload
    if payload_changed and sync.status != SYNC_PENDING:
        sync.status = SYNC_PENDING
        sync.attempt_count = 0
        sync.last_error = None
        sync.synced_at = None
    db.flush()
    return sync


def applicant_sync_payload(sync: OdooApplicantSync) -> dict:
    return {
        "id": sync.id,
        "job_candidate_id": sync.job_candidate_id,
        "idempotency_key": sync.idempotency_key,
        "status": sync.status,
        "attempt_count": sync.attempt_count,
        "odoo_job_id": sync.odoo_job_id,
        "odoo_applicant_id": sync.odoo_applicant_id,
        "last_error": sync.last_error,
        "synced_at": _iso(sync.synced_at),
        "created_at": _iso(sync.created_at),
        "updated_at": _iso(sync.updated_at),
    }


def build_employee_upsert_payload(
    *,
    employee: UserProfile,
    candidate: Candidate,
    job: Job,
    application: JobCandidate,
) -> dict:
    """Build the stable versioned contract that will later be sent to Odoo."""

    return {
        "schema_version": 1,
        "operation": "UPSERT_EMPLOYEE",
        "source": {
            "employee_id": employee.id,
            "candidate_id": candidate.id,
            "job_id": job.id,
            "application_id": application.id,
            "hired_at": _iso(application.hired_at),
        },
        "employee": {
            "first_name": employee.first_name,
            "last_name": employee.last_name,
            "name": " ".join(
                part
                for part in (employee.first_name, employee.last_name)
                if part
            ).strip(),
            "email": employee.email,
            "job_title": employee.job_title,
            "department": employee.department,
            "hire_date": _iso(employee.hire_date),
        },
        "candidate": {
            "name": candidate.name,
            "email": candidate.email,
            "phone": _candidate_phone(candidate),
        },
        "job": {
            "title": job.title,
            "country_code": job.country_code,
            "city": job.city,
            "employment_type": job.employment_type,
        },
    }


def ensure_employee_sync(
    db: Session,
    *,
    employee: UserProfile,
    candidate: Candidate,
    job: Job,
    application: JobCandidate,
) -> OdooEmployeeSync:
    """Create or refresh the single idempotent Odoo upsert state for an employee."""

    payload = build_employee_upsert_payload(
        employee=employee,
        candidate=candidate,
        job=job,
        application=application,
    )
    sync = (
        db.query(OdooEmployeeSync)
        .filter(OdooEmployeeSync.employee_id == employee.id)
        .one_or_none()
    )
    if sync is None:
        sync = OdooEmployeeSync(
            employee_id=employee.id,
            source_job_candidate_id=application.id,
            idempotency_key=f"employee:{employee.id}",
            payload=payload,
            status=SYNC_PENDING,
        )
        db.add(sync)
        db.flush()
        return sync

    payload_changed = sync.payload != payload
    sync.source_job_candidate_id = application.id
    sync.payload = payload
    if payload_changed and sync.status != SYNC_PENDING:
        sync.status = SYNC_PENDING
        sync.attempt_count = 0
        sync.last_error = None
        sync.synced_at = None
    db.flush()
    return sync


def sync_payload(sync: OdooEmployeeSync) -> dict:
    return {
        "id": sync.id,
        "employee_id": sync.employee_id,
        "source_job_candidate_id": sync.source_job_candidate_id,
        "idempotency_key": sync.idempotency_key,
        "status": sync.status,
        "attempt_count": sync.attempt_count,
        "odoo_record_id": sync.odoo_record_id,
        "last_error": sync.last_error,
        "synced_at": _iso(sync.synced_at),
        "created_at": _iso(sync.created_at),
        "updated_at": _iso(sync.updated_at),
    }
