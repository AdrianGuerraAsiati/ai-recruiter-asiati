"""Delivery of selected applications from the durable outbox to Odoo."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.domains.odoo_sync import integration
from app.infrastructure.imports import storage as candidate_storage
from app.integrations.odoo.client import OdooClientError
from app.models import OdooApplicantSync

ODOO_COMPANY_NAME = "ASIATI"
ODOO_SELECTED_STAGE_NAME = "Initial Qualification"


class OdooApplicantSyncNotFound(LookupError):
    pass


class OdooApplicantSyncConflict(RuntimeError):
    pass


class OdooApplicantDeliveryError(RuntimeError):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def require_applicant_sync(db: Session, application_id: str) -> OdooApplicantSync:
    sync = (
        db.query(OdooApplicantSync)
        .filter(OdooApplicantSync.job_candidate_id == application_id)
        .one_or_none()
    )
    if sync is None:
        raise OdooApplicantSyncNotFound(application_id)
    return sync


def _writable_fields(client, model: str) -> dict[str, dict[str, Any]]:
    fields = client.fields_get(
        model,
        attributes=("string", "type", "required", "readonly", "relation", "selection"),
    )
    return {
        name: dict(metadata or {})
        for name, metadata in fields.items()
        if not bool((metadata or {}).get("readonly"))
    }


def _stored_record_id(client, model: str, value: str | None) -> int | None:
    raw = str(value or "").strip()
    if not raw.isdigit():
        return None
    record_id = int(raw)
    rows = client.search_read(model, [["id", "=", record_id]], fields=["id"], limit=1)
    return record_id if rows else None


def _exact_named_id(client, model: str, name: str) -> int | None:
    rows = client.search_read(
        model,
        [["name", "=ilike", name]],
        fields=["id", "name"],
        limit=10,
    )
    exact = [
        row for row in rows
        if str(row.get("name") or "").strip().casefold() == name.casefold()
    ]
    return int(exact[0]["id"]) if len(exact) == 1 else None


def _company_id(client) -> int:
    company_id = _exact_named_id(client, "res.company", ODOO_COMPANY_NAME)
    if company_id is None:
        raise OdooApplicantDeliveryError(
            "Odoo company ASIATI could not be resolved unambiguously."
        )
    return company_id


def _upsert_job(client, sync: OdooApplicantSync, payload: dict, company_id: int):
    job = dict(payload.get("job") or {})
    title = str(job.get("title") or "").strip()
    if not title:
        raise OdooApplicantDeliveryError("Job title is required for Odoo.")

    writable = _writable_fields(client, "hr.job")
    values = {"name": title}
    if "company_id" in writable:
        values["company_id"] = company_id
    description = str(job.get("description") or "").strip()
    if description and "description" in writable:
        values["description"] = description

    existing_id = _stored_record_id(client, "hr.job", sync.odoo_job_id)
    if existing_id is not None:
        client.write("hr.job", [existing_id], values)
        return existing_id, "UPDATED", sorted(values)

    rows = client.search_read(
        "hr.job",
        [["name", "=ilike", title], ["company_id", "=", company_id]],
        fields=["id", "name"],
        limit=3,
    )
    exact = [
        row for row in rows
        if str(row.get("name") or "").strip().casefold() == title.casefold()
    ]
    if len(exact) > 1:
        raise OdooApplicantSyncConflict(
            "Multiple Odoo jobs match the selected vacancy."
        )
    if exact:
        return int(exact[0]["id"]), "REUSED", []

    return int(client.create("hr.job", values)), "CREATED", sorted(values)


def _applicant_values(client, payload: dict, job_id: int, company_id: int):
    candidate = dict(payload.get("candidate") or {})
    name = str(candidate.get("name") or "").strip()
    email = str(candidate.get("email") or "").strip()
    phone = str(candidate.get("phone") or "").strip()
    if not name:
        raise OdooApplicantDeliveryError("Candidate name is required for Odoo.")

    writable = _writable_fields(client, "hr.applicant")
    values = {"partner_name": name, "job_id": job_id, "company_id": company_id}
    if email and "email_from" in writable:
        values["email_from"] = email
    if phone and "partner_phone" in writable:
        values["partner_phone"] = phone

    stage_id = _exact_named_id(
        client, "hr.recruitment.stage", ODOO_SELECTED_STAGE_NAME
    )
    if stage_id is not None and "stage_id" in writable:
        values["stage_id"] = stage_id

    return values, email, phone


def _find_applicant(client, sync, job_id: int, company_id: int, email: str, phone: str):
    stored_id = _stored_record_id(client, "hr.applicant", sync.odoo_applicant_id)
    if stored_id is not None:
        return stored_id

    if email:
        domain = [
            ["job_id", "=", job_id],
            ["company_id", "=", company_id],
            ["email_from", "=ilike", email],
        ]
    elif phone:
        domain = [
            ["job_id", "=", job_id],
            ["company_id", "=", company_id],
            ["partner_phone", "=", phone],
        ]
    else:
        raise OdooApplicantDeliveryError(
            "Candidate email or phone is required for idempotent Odoo synchronization."
        )

    rows = client.search_read(
        "hr.applicant", domain, fields=["id"], limit=2
    )
    if len(rows) > 1:
        raise OdooApplicantSyncConflict(
            "Multiple Odoo applicants match the selected candidate and job."
        )
    return int(rows[0]["id"]) if rows else None


def _upsert_applicant(client, sync, payload: dict, job_id: int, company_id: int):
    values, email, phone = _applicant_values(client, payload, job_id, company_id)
    existing_id = _find_applicant(
        client, sync, job_id, company_id, email, phone
    )
    if existing_id is None:
        return int(client.create("hr.applicant", values)), "CREATED", sorted(values)
    client.write("hr.applicant", [existing_id], values)
    return existing_id, "UPDATED", sorted(values)


def _sync_cv(
    client,
    payload: dict,
    applicant_id: int,
    company_id: int,
    document_loader: Callable[[str], Any | None],
):
    candidate_id = str(
        (payload.get("candidate") or {}).get("external_id") or ""
    ).strip()
    document = document_loader(candidate_id) if candidate_id else None
    if document is None:
        raise OdooApplicantDeliveryError(
            "Canonical candidate CV was not found."
        )

    writable = _writable_fields(client, "ir.attachment")
    values = {
        "name": document.filename,
        "datas": base64.b64encode(document.data).decode("ascii"),
        "res_model": "hr.applicant",
        "res_id": applicant_id,
    }
    if "description" in writable:
        values["description"] = f"CV aiRecruiter ({candidate_id})"
    if "company_id" in writable:
        values["company_id"] = company_id

    rows = client.search_read(
        "ir.attachment",
        [
            ["res_model", "=", "hr.applicant"],
            ["res_id", "=", applicant_id],
            ["name", "=", document.filename],
        ],
        fields=["id"],
        limit=2,
    )
    if len(rows) > 1:
        raise OdooApplicantSyncConflict(
            "Multiple Odoo attachments match the canonical CV."
        )
    if rows:
        attachment_id = int(rows[0]["id"])
        client.write("ir.attachment", [attachment_id], values)
        action = "UPDATED"
    else:
        attachment_id = int(client.create("ir.attachment", values))
        action = "CREATED"
    return {
        "action": action,
        "odoo_attachment_id": attachment_id,
        "filename": document.filename,
    }


def sync_applicant_now(
    db: Session,
    *,
    application_id: str,
    client=None,
    document_loader: Callable[[str], Any | None] | None = None,
) -> dict:
    """Synchronize one selected application, vacancy and canonical CV."""

    sync = require_applicant_sync(db, application_id)
    transport = client or integration.build_odoo_client()
    loader = document_loader or candidate_storage.read_canonical_candidate_document

    sync.attempt_count = int(sync.attempt_count or 0) + 1
    sync.status = "PENDING"
    sync.last_error = None
    db.commit()
    db.refresh(sync)

    try:
        payload = dict(sync.payload or {})
        company_id = _company_id(transport)
        job_id, job_action, job_fields = _upsert_job(
            transport, sync, payload, company_id
        )
        sync.odoo_job_id = str(job_id)
        db.commit()
        db.refresh(sync)

        applicant_id, applicant_action, applicant_fields = _upsert_applicant(
            transport, sync, payload, job_id, company_id
        )
        sync.odoo_applicant_id = str(applicant_id)
        db.commit()
        db.refresh(sync)

        attachment = _sync_cv(
            transport, payload, applicant_id, company_id, loader
        )
        sync.status = "SYNCED"
        sync.last_error = None
        sync.synced_at = _utcnow()
        db.commit()
        db.refresh(sync)
        return {
            "application_id": sync.job_candidate_id,
            "status": sync.status,
            "attempt_count": sync.attempt_count,
            "company_id": company_id,
            "odoo_job_id": sync.odoo_job_id,
            "odoo_applicant_id": sync.odoo_applicant_id,
            "job": {"action": job_action, "fields_written": job_fields},
            "applicant": {
                "action": applicant_action,
                "fields_written": applicant_fields,
            },
            "attachment": attachment,
            "synced_at": sync.synced_at.isoformat() if sync.synced_at else None,
        }
    except (OdooApplicantDeliveryError, OdooApplicantSyncConflict, OdooClientError) as exc:
        sync.status = "FAILED"
        sync.last_error = str(exc)
        sync.synced_at = None
        db.commit()
        raise OdooApplicantDeliveryError(str(exc)) from exc
    except Exception as exc:
        sync.status = "FAILED"
        sync.last_error = "ODOO_APPLICANT_SYNC_FAILED"
        sync.synced_at = None
        db.commit()
        raise OdooApplicantDeliveryError("ODOO_APPLICANT_SYNC_FAILED") from exc
