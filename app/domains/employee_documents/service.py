"""Employee self-service profile and requested-document service."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.domains.employee_documents.models import (
    EmployeeDocumentRequest,
    EmployeePersonalProfile,
)
from app.infrastructure.storage import employee_documents as storage
from app.models import UserProfile


MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}


class EmployeeSelfServiceError(ValueError):
    pass


class EmployeeDocumentNotFound(LookupError):
    pass


def _employee(db: Session, employee_id: str) -> UserProfile:
    employee = (
        db.query(UserProfile)
        .filter(UserProfile.id == employee_id)
        .one_or_none()
    )
    if employee is None:
        raise EmployeeDocumentNotFound(employee_id)
    return employee


def _personal_profile(
    db: Session,
    employee_id: str,
    *,
    create: bool,
) -> EmployeePersonalProfile | None:
    profile = (
        db.query(EmployeePersonalProfile)
        .filter(EmployeePersonalProfile.employee_id == employee_id)
        .one_or_none()
    )
    if profile is None and create:
        profile = EmployeePersonalProfile(employee_id=employee_id)
        db.add(profile)
        db.flush()
    return profile


def own_profile_payload(db: Session, employee_id: str) -> dict:
    employee = _employee(db, employee_id)
    personal = _personal_profile(db, employee_id, create=False)
    return {
        "employee_id": employee.id,
        "first_name": employee.first_name,
        "last_name": employee.last_name,
        "work_email": employee.email,
        "job_title": employee.job_title,
        "department": employee.department,
        "hire_date": employee.hire_date.isoformat() if employee.hire_date else None,
        "personal_email": personal.personal_email if personal else None,
        "phone": personal.phone if personal else None,
        "address": personal.address if personal else None,
        "city": personal.city if personal else None,
        "emergency_contact_name": (
            personal.emergency_contact_name if personal else None
        ),
        "emergency_contact_phone": (
            personal.emergency_contact_phone if personal else None
        ),
    }


def update_own_profile(
    db: Session,
    *,
    employee_id: str,
    changes: dict,
    actor_sub: str,
) -> dict:
    employee = _employee(db, employee_id)
    personal = _personal_profile(db, employee_id, create=True)

    for field in ("first_name", "last_name"):
        if field in changes:
            setattr(employee, field, changes[field])

    for field in (
        "personal_email",
        "phone",
        "address",
        "city",
        "emergency_contact_name",
        "emergency_contact_phone",
    ):
        if field in changes:
            setattr(personal, field, changes[field])

    personal.updated_by_sub = actor_sub
    db.commit()
    return own_profile_payload(db, employee_id)


def document_payload(item: EmployeeDocumentRequest) -> dict:
    return {
        "id": item.id,
        "employee_id": item.employee_id,
        "label": item.label,
        "document_type": item.document_type,
        "required": bool(item.required),
        "status": item.status,
        "has_file": bool(item.storage_key),
        "original_filename": item.original_filename,
        "content_type": item.content_type,
        "size_bytes": item.size_bytes,
        "sha256": item.sha256,
        "uploaded_at": item.uploaded_at.isoformat() if item.uploaded_at else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def list_document_requests(db: Session, employee_id: str) -> list[dict]:
    _employee(db, employee_id)
    rows = (
        db.query(EmployeeDocumentRequest)
        .filter(EmployeeDocumentRequest.employee_id == employee_id)
        .order_by(
            EmployeeDocumentRequest.required.desc(),
            EmployeeDocumentRequest.created_at.asc(),
        )
        .all()
    )
    return [document_payload(item) for item in rows]


def create_document_request(
    db: Session,
    *,
    employee_id: str,
    label: str,
    document_type: str | None,
    required: bool,
    requested_by_sub: str,
) -> dict:
    _employee(db, employee_id)
    item = EmployeeDocumentRequest(
        employee_id=employee_id,
        label=label.strip(),
        document_type=(document_type or "").strip() or None,
        required=bool(required),
        requested_by_sub=requested_by_sub,
        status="PENDING",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return document_payload(item)


def _request(
    db: Session,
    *,
    employee_id: str,
    request_id: str,
) -> EmployeeDocumentRequest:
    item = (
        db.query(EmployeeDocumentRequest)
        .filter(
            EmployeeDocumentRequest.id == request_id,
            EmployeeDocumentRequest.employee_id == employee_id,
        )
        .one_or_none()
    )
    if item is None:
        raise EmployeeDocumentNotFound(request_id)
    return item


def _validate_file(filename: str, content_type: str, payload: bytes) -> None:
    if not payload:
        raise EmployeeSelfServiceError("El archivo está vacío.")
    if len(payload) > MAX_DOCUMENT_BYTES:
        raise EmployeeSelfServiceError("El archivo supera el límite de 10 MB.")
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise EmployeeSelfServiceError(
            "Formato no permitido. Usa PDF, JPG, PNG o DOCX."
        )

    lower = filename.casefold()
    expected = ALLOWED_CONTENT_TYPES[content_type]
    if content_type == "image/jpeg":
        valid_extension = lower.endswith((".jpg", ".jpeg"))
    else:
        valid_extension = lower.endswith(expected)
    if not valid_extension:
        raise EmployeeSelfServiceError(
            "La extensión del archivo no coincide con su formato."
        )

    signatures = {
        "application/pdf": payload.startswith(b"%PDF-"),
        "image/jpeg": payload.startswith(b"\xff\xd8\xff"),
        "image/png": payload.startswith(b"\x89PNG\r\n\x1a\n"),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (
            payload.startswith(b"PK")
        ),
    }
    if not signatures[content_type]:
        raise EmployeeSelfServiceError("El contenido del archivo no es válido.")


def upload_document(
    db: Session,
    *,
    employee_id: str,
    request_id: str,
    filename: str,
    content_type: str,
    payload: bytes,
    actor_sub: str,
) -> dict:
    item = _request(db, employee_id=employee_id, request_id=request_id)
    _validate_file(filename, content_type, payload)

    old_key = item.storage_key
    new_key = storage.put_employee_document(
        employee_id=employee_id,
        request_id=request_id,
        filename=filename,
        content_type=content_type,
        payload=payload,
    )
    try:
        item.storage_key = new_key
        item.original_filename = storage.safe_filename(filename)
        item.content_type = content_type
        item.size_bytes = len(payload)
        item.sha256 = hashlib.sha256(payload).hexdigest()
        item.uploaded_by_sub = actor_sub
        item.uploaded_at = datetime.now(timezone.utc)
        item.status = "UPLOADED"
        db.commit()
        db.refresh(item)
    except Exception:
        db.rollback()
        storage.delete_employee_document(new_key)
        raise

    if old_key and old_key != new_key:
        try:
            storage.delete_employee_document(old_key)
        except Exception:
            pass
    return document_payload(item)


def download_document(
    db: Session,
    *,
    employee_id: str,
    request_id: str,
) -> tuple[bytes, str, str]:
    item = _request(db, employee_id=employee_id, request_id=request_id)
    if not item.storage_key or not item.original_filename:
        raise EmployeeDocumentNotFound(request_id)
    payload, stored_content_type = storage.get_employee_document(item.storage_key)
    return (
        payload,
        item.original_filename,
        item.content_type or stored_content_type or "application/octet-stream",
    )
