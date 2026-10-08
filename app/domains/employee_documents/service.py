"""Business logic for private employee documents."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.domains.employee_documents.models import EmployeeDocument
from app.infrastructure.storage import employee_documents as storage
from app.models import UserProfile

logger = logging.getLogger(__name__)


class EmployeeDocumentNotFound(Exception):
    pass


class EmployeeNotFound(Exception):
    pass


def normalize_document_type(value: str) -> str:
    normalized = " ".join(str(value or "").strip().split())
    if not normalized or len(normalized) > 80:
        raise ValueError("Tipo de documento inválido.")
    return normalized


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


def document_payload(document: EmployeeDocument) -> dict:
    return {
        "id": document.id,
        "employee_id": document.employee_id,
        "document_type": document.document_type,
        "original_filename": document.original_filename,
        "content_type": document.content_type,
        "size_bytes": document.size_bytes,
        "uploaded_at": document.uploaded_at.isoformat() if document.uploaded_at else None,
    }


def list_documents(db: Session, employee_id: str) -> list[dict]:
    require_employee(db, employee_id)
    rows = (
        db.query(EmployeeDocument)
        .filter(EmployeeDocument.employee_id == employee_id)
        .order_by(EmployeeDocument.document_type.asc())
        .all()
    )
    return [document_payload(row) for row in rows]


def create_upload(
    db: Session,
    *,
    employee_id: str,
    document_type: str,
    filename: str,
    content_type: str,
    size_bytes: int,
) -> dict:
    require_employee(db, employee_id)
    normalize_document_type(document_type)
    return storage.create_document_upload(
        employee_id=employee_id,
        filename=filename,
        content_type=content_type,
        size_bytes=size_bytes,
    )


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
) -> EmployeeDocument:
    require_employee(db, employee_id)
    normalized_document_type = normalize_document_type(document_type)
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
    previous_key = existing.storage_key if existing else None
    document = existing or EmployeeDocument(
        employee_id=employee_id,
        document_type=normalized_document_type,
    )
    document.original_filename = filename.replace("\\", "/").rsplit("/", 1)[-1]
    document.storage_key = verified["key"]
    document.content_type = verified["content_type"]
    document.size_bytes = verified["size_bytes"]
    document.uploaded_by_sub = uploaded_by_sub
    document.uploaded_at = datetime.now(timezone.utc)
    if existing is None:
        db.add(document)

    db.commit()
    db.refresh(document)

    if previous_key and previous_key != document.storage_key:
        try:
            storage.delete_document_object(previous_key)
        except Exception:
            logger.warning("Could not delete replaced employee document %s", previous_key, exc_info=True)
    return document


def download_payload(db: Session, document_id: str) -> dict:
    document = require_document(db, document_id)
    return {
        "url": storage.create_document_download_url(
            document.storage_key,
            filename=document.original_filename,
        ),
        "filename": document.original_filename,
        "expires_in": storage.PRESIGNED_DOWNLOAD_EXPIRY_SECONDS,
    }
