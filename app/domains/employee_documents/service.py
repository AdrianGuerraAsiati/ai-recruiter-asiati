"""Business logic for new-employee intake document review."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session

from app.domains.employee_documents.models import EmployeeDocument
from app.domains.employee_documents.requirements import (
    EMPLOYEE_DOCUMENT_REQUIREMENTS,
    get_requirement,
)
from app.infrastructure.storage import employee_documents as storage
from app.models import UserProfile, JobCandidate, Job, Candidate

logger = logging.getLogger(__name__)


class EmployeeDocumentNotFound(Exception):
    pass


class EmployeeNotFound(Exception):
    pass


def normalize_document_type(value: str) -> str:
    normalized = str(value or "").strip().upper()
    if not get_requirement(normalized):
        raise ValueError("Este requisito no hace parte del expediente de ingreso.")
    return normalized


def _require_kind(document_type: str, kind: str, *, admin_upload: bool = False) -> dict:
    normalized = normalize_document_type(document_type)
    requirement = get_requirement(normalized)
    if requirement.get("admin_only") and not admin_upload:
        raise ValueError("Este documento solo puede cargarlo Talento Humano.")
    if requirement["kind"] != kind:
        if kind == "FILE":
            raise ValueError("Este requisito se completa como información y no como archivo.")
        raise ValueError("Este requisito debe completarse cargando un archivo.")
    return requirement


def require_employee(db: Session, employee_id: str) -> UserProfile:
    employee = db.query(UserProfile).filter(UserProfile.id == employee_id).one_or_none()
    if employee is None:
        raise EmployeeNotFound()
    return employee


def require_document(db: Session, document_id: str) -> EmployeeDocument:
    document = (
        db.query(EmployeeDocument)
        .filter(EmployeeDocument.id == document_id)
        .one_or_none()
    )
    if document is None:
        raise EmployeeDocumentNotFound()
    return document


def _missing_payload(requirement: dict) -> dict:
    return {
        "id": None,
        "employee_id": None,
        "document_type": requirement["value"],
        "label": requirement["label"],
        "kind": requirement["kind"],
        "description": requirement["description"],
        "admin_only": bool(requirement.get("admin_only")),
        "original_filename": None,
        "content_type": None,
        "size_bytes": None,
        "value_text": None,
        "uploaded_at": None,
        "review_status": "MISSING",
        "review_comment": None,
        "reviewed_at": None,
    }


def document_payload(document: EmployeeDocument) -> dict:
    requirement = get_requirement(document.document_type)
    if requirement is None:
        requirement = {
            "value": document.document_type,
            "label": document.document_type,
            "kind": "FILE" if document.storage_key else "TEXT",
            "description": "",
        }
    return {
        "id": document.id,
        "employee_id": document.employee_id,
        "document_type": requirement["value"],
        "label": requirement["label"],
        "kind": requirement["kind"],
        "description": requirement["description"],
        "admin_only": bool(requirement.get("admin_only")),
        "original_filename": document.original_filename,
        "content_type": document.content_type,
        "size_bytes": document.size_bytes,
        "value_text": document.value_text,
        "uploaded_at": document.uploaded_at.isoformat() if document.uploaded_at else None,
        "review_status": document.review_status or "PENDING_REVIEW",
        "review_comment": document.review_comment,
        "reviewed_at": document.reviewed_at.isoformat() if document.reviewed_at else None,
        "odoo_sign_status": document.odoo_sign_status if document.document_type == "EMPLOYMENT_CONTRACT" else None,
        "odoo_sign_prepared_at": (
            document.odoo_sign_prepared_at.isoformat() if document.odoo_sign_prepared_at else None
        ),
    }


def list_documents(db: Session, employee_id: str, *, include_admin_only: bool = False) -> list[dict]:
    require_employee(db, employee_id)
    rows = (
        db.query(EmployeeDocument)
        .filter(EmployeeDocument.employee_id == employee_id)
        .all()
    )
    by_type = {row.document_type: row for row in rows}
    items = []
    for requirement in EMPLOYEE_DOCUMENT_REQUIREMENTS:
        if requirement.get("admin_only") and not include_admin_only:
            continue
        row = by_type.get(requirement["value"])
        items.append(document_payload(row) if row else _missing_payload(requirement))
    return items


def _summary(items: list[dict]) -> dict:
    total = len(items)
    approved = sum(item["review_status"] == "APPROVED" for item in items)
    pending_review = sum(item["review_status"] == "PENDING_REVIEW" for item in items)
    changes_requested = sum(item["review_status"] == "CHANGES_REQUESTED" for item in items)
    missing = sum(item["review_status"] == "MISSING" for item in items)
    submitted = total - missing
    if total and approved == total:
        status = "APPROVED"
    elif changes_requested:
        status = "CHANGES_REQUESTED"
    elif pending_review:
        status = "PENDING_REVIEW"
    else:
        status = "INCOMPLETE"
    return {
        "total": total,
        "submitted": submitted,
        "approved": approved,
        "pending_review": pending_review,
        "changes_requested": changes_requested,
        "missing": missing,
        "approval_percent": round((approved / total) * 100) if total else 0,
        "status": status,
    }


def portfolio_payload(db: Session, employee_id: str, *, include_admin_only: bool = False) -> dict:
    employee = require_employee(db, employee_id)
    items = list_documents(db, employee_id, include_admin_only=include_admin_only)
    return {
        "employee": {
            "id": employee.id,
            "first_name": employee.first_name,
            "last_name": employee.last_name,
            "email": employee.email,
        },
        "items": items,
        "total": len(items),
        "summary": _summary(items),
    }


def create_upload(
    db: Session,
    *,
    employee_id: str,
    document_type: str,
    filename: str,
    content_type: str,
    size_bytes: int,
    admin_upload: bool = False,
) -> dict:
    require_employee(db, employee_id)
    requirement = _require_kind(document_type, "FILE", admin_upload=admin_upload)
    upload = storage.create_document_upload(
        employee_id=employee_id,
        filename=filename,
        content_type=content_type,
        size_bytes=size_bytes,
    )
    upload["document_type"] = requirement["value"]
    return upload


def finalize_upload(
    db: Session,
    *,
    employee_id: str,
    uploaded_by_sub: str,
    document_type: str,
    filename: str,
    key: str,
    content_type: str,
    size_bytes: int,
    admin_upload: bool = False,
) -> EmployeeDocument:
    require_employee(db, employee_id)
    requirement = _require_kind(document_type, "FILE", admin_upload=admin_upload)
    normalized_document_type = requirement["value"]
    verified = storage.verify_document_object(
        employee_id=employee_id,
        key=key,
        expected_content_type=content_type,
        expected_size_bytes=size_bytes,
    )

    existing = (
        db.query(EmployeeDocument)
        .filter(
            EmployeeDocument.employee_id == employee_id,
            EmployeeDocument.document_type == normalized_document_type,
        )
        .one_or_none()
    )
    if existing and existing.odoo_sign_request_id is not None:
        raise ValueError("Existe una solicitud de firma vinculada. No se permite reemplazar el contrato.")
    if existing and existing.odoo_sign_status in ("PREPARING", "PREPARED"):
        raise ValueError(
            "El contrato ya está en preparación en Odoo Sign. No se permite reemplazar "
            "el archivo para evitar versiones distintas de un contrato a firmar."
        )
    previous_key = existing.storage_key if existing else None
    document = existing or EmployeeDocument(
        employee_id=employee_id,
        document_type=normalized_document_type,
    )
    document.original_filename = filename.replace("\\", "/").rsplit("/", 1)[-1]
    document.storage_key = verified["key"]
    document.content_type = verified["content_type"]
    document.size_bytes = verified["size_bytes"]
    document.value_text = None
    document.uploaded_by_sub = uploaded_by_sub
    document.uploaded_at = datetime.now(timezone.utc)
    document.review_status = "PENDING_REVIEW"
    if normalized_document_type == "EMPLOYMENT_CONTRACT":
        document.odoo_sign_status = "NOT_PREPARED"
        document.odoo_sign_source_key = None
        document.odoo_sign_template_id = None
        document.odoo_sign_attachment_id = None
        document.odoo_sign_prepared_at = None
        document.odoo_sign_request_id = None
        document.odoo_sign_request_status = "UNLINKED"
        document.odoo_sign_employee_state = None
        document.odoo_sign_representative_state = None
        document.odoo_sign_checked_at = None
        document.odoo_sign_completed_at = None
    document.reviewed_by_sub = None
    document.reviewed_at = None
    if existing is None:
        db.add(document)

    db.commit()
    db.refresh(document)

    if previous_key and previous_key != document.storage_key:
        try:
            storage.delete_document_object(previous_key)
        except Exception:
            logger.warning(
                "Could not delete replaced employee document %s",
                previous_key,
                exc_info=True,
            )
    return document


def save_value(
    db: Session,
    *,
    employee_id: str,
    uploaded_by_sub: str,
    document_type: str,
    value: str,
) -> EmployeeDocument:
    require_employee(db, employee_id)
    requirement = _require_kind(document_type, "TEXT")
    normalized_value = " ".join(str(value or "").strip().split())
    if not normalized_value:
        raise ValueError("Completa la información antes de enviarla.")

    existing = (
        db.query(EmployeeDocument)
        .filter(
            EmployeeDocument.employee_id == employee_id,
            EmployeeDocument.document_type == requirement["value"],
        )
        .one_or_none()
    )
    document = existing or EmployeeDocument(
        employee_id=employee_id,
        document_type=requirement["value"],
    )
    document.original_filename = None
    document.storage_key = None
    document.content_type = None
    document.size_bytes = None
    document.value_text = normalized_value
    document.uploaded_by_sub = uploaded_by_sub
    document.uploaded_at = datetime.now(timezone.utc)
    document.review_status = "PENDING_REVIEW"
    document.reviewed_by_sub = None
    document.reviewed_at = None
    if existing is None:
        db.add(document)

    db.commit()
    db.refresh(document)
    return document


def review_document(
    db: Session,
    *,
    document_id: str,
    status: str,
    comment: str | None,
    reviewed_by_sub: str,
) -> EmployeeDocument:
    document = require_document(db, document_id)
    normalized_status = str(status or "").strip().upper()
    normalized_comment = str(comment or "").strip() or None
    if normalized_status not in {"APPROVED", "CHANGES_REQUESTED"}:
        raise ValueError("Estado de revisión inválido.")
    if normalized_status == "CHANGES_REQUESTED" and not normalized_comment:
        raise ValueError("Escribe un comentario indicando qué debe corregir el empleado.")

    document.review_status = normalized_status
    document.review_comment = normalized_comment
    document.reviewed_by_sub = reviewed_by_sub
    document.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(document)
    return document


def download_payload(db: Session, document_id: str) -> dict:
    document = require_document(db, document_id)
    if not document.storage_key or not document.original_filename:
        raise EmployeeDocumentNotFound()
    return {
        "url": storage.create_document_download_url(
            document.storage_key,
            filename=document.original_filename,
        ),
        "filename": document.original_filename,
        "expires_in": storage.PRESIGNED_DOWNLOAD_EXPIRY_SECONDS,
    }


def review_queue(db: Session, *, limit: int = 100) -> dict:
    """Administrative inbox of pending and correction-requested document sets.

    Only persons with documents needing attention appear; applicants without
    any submission are still reachable through the Applications deep link.
    """
    pending = func.sum(case((EmployeeDocument.review_status == "PENDING_REVIEW", 1), else_=0))
    corrections = func.sum(case((EmployeeDocument.review_status == "CHANGES_REQUESTED", 1), else_=0))
    rows = (
        db.query(
            UserProfile.id,
            UserProfile.first_name,
            UserProfile.last_name,
            UserProfile.email,
            pending.label("pending"),
            corrections.label("corrections"),
            func.max(EmployeeDocument.uploaded_at).label("last_submission_at"),
        )
        .join(EmployeeDocument, EmployeeDocument.employee_id == UserProfile.id)
        .filter(EmployeeDocument.review_status.in_(("PENDING_REVIEW", "CHANGES_REQUESTED")))
        .group_by(UserProfile.id, UserProfile.first_name, UserProfile.last_name, UserProfile.email)
        .order_by(
            func.max(EmployeeDocument.uploaded_at).desc(),
            UserProfile.id.asc(),
        )
        .limit(min(max(int(limit), 1), 100))
        .all()
    )
    return {
        "items": [
            {
                "profile_id": profile_id,
                "name": " ".join(x for x in (first_name, last_name) if x) or email or "Postulante",
                "email": email,
                "pending_review": int(pending_count or 0),
                "changes_requested": int(corrections_count or 0),
                "last_submission_at": last_submission_at.isoformat() if last_submission_at else None,
            }
            for profile_id, first_name, last_name, email, pending_count, corrections_count, last_submission_at in rows
        ],
        "limit": min(max(int(limit), 1), 100),
    }


def application_select_options(db: Session, *, query: str = "", limit: int = 250) -> dict:
    """Active applications with a document profile, not the employee directory.

    Each option identifies a vacancy application even when candidates share a
    profile. Applicant documents are presently stored against that profile.
    """
    search = str(query or "").strip()[:120]
    upper_limit = min(max(int(limit), 1), 250)
    rows = (
        db.query(JobCandidate, Candidate, Job, UserProfile)
        .join(Candidate, JobCandidate.candidate_id == Candidate.id)
        .join(Job, JobCandidate.job_id == Job.id)
        .join(UserProfile, JobCandidate.employee_id == UserProfile.id)
        .filter(
            JobCandidate.employee_id.isnot(None),
            JobCandidate.application_status.notin_(("HIRED", "REJECTED", "WITHDRAWN")),
        )
    )
    if search:
        pattern = f"%{search}%"
        rows = rows.filter(or_(
            Candidate.name.ilike(pattern),
            UserProfile.email.ilike(pattern),
            Job.title.ilike(pattern),
        ))
    result = rows.order_by(JobCandidate.assigned_at.desc(), JobCandidate.id.asc()).limit(upper_limit).all()
    return {
        "items": [{
            "application_id": link.id,
            "profile_id": person.id,
            "name": candidate.name,
            "email": person.email,
            "job_title": job.title,
            "status": link.application_status,
        } for link, candidate, job, person in result],
        "limit": upper_limit,
    }
