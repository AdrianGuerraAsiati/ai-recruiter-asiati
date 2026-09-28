"""Durable Odoo employee synchronization outbox.

This module deliberately prepares and persists the synchronization contract without
performing network I/O. Transport to Odoo is a separate concern so hiring remains
successful even when Odoo is unavailable.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Candidate, Job, JobCandidate, OdooEmployeeSync, UserProfile


SYNC_PENDING = "PENDING"
SYNC_SYNCED = "SYNCED"
SYNC_FAILED = "FAILED"


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


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
