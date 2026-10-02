"""Employee document lifecycle and immutable signed evidence."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import uuid

import fitz
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import OdooContractSync, UserProfile
from app.domains.employee_documents.models import (
    EmployeeDocument,
    EmployeeDocumentArtifact,
    EmployeeDocumentVersion,
)
from app.domains.employee_documents.storage import (
    EmployeeDocumentStorage,
    signed_version_key,
)


class EmployeeDocumentNotFound(LookupError):
    pass


class EmployeeDocumentValidationError(ValueError):
    pass


class EmployeeDocumentStateError(RuntimeError):
    pass


class EmployeeDocumentStorageError(RuntimeError):
    pass


_ALLOWED_DOCUMENT_TYPES = {"CONTRACT", "ADDENDUM", "OTHER"}


def _require_employee(db: Session, employee_id: str) -> UserProfile:
    employee = db.query(UserProfile).filter(UserProfile.id == employee_id).one_or_none()
    if employee is None:
        raise EmployeeDocumentNotFound("Empleado no encontrado.")
    return employee


def _require_document(
    db: Session,
    *,
    employee_id: str,
    document_id: str,
    for_update: bool = False,
) -> EmployeeDocument:
    query = db.query(EmployeeDocument).filter(
        EmployeeDocument.id == document_id,
        EmployeeDocument.employee_id == employee_id,
    )
    if for_update:
        query = query.with_for_update()
    document = query.one_or_none()
    if document is None:
        raise EmployeeDocumentNotFound("Documento no encontrado.")
    return document


def create_document(
    db: Session,
    *,
    employee_id: str,
    document_type: str,
    title: str,
    created_by_sub: str,
    contract_sync_id: str | None = None,
    source_job_candidate_id: str | None = None,
) -> EmployeeDocument:
    _require_employee(db, employee_id)
    normalized_type = str(document_type or "").strip().upper()
    normalized_title = str(title or "").strip()
    if normalized_type not in _ALLOWED_DOCUMENT_TYPES:
        raise EmployeeDocumentValidationError("Tipo de documento no válido.")
    if not normalized_title:
        raise EmployeeDocumentValidationError("El título del documento es obligatorio.")

    document = EmployeeDocument(
        id=str(uuid.uuid4()),
        employee_id=employee_id,
        document_type=normalized_type,
        title=normalized_title,
        status="DRAFT",
        contract_sync_id=contract_sync_id,
        source_job_candidate_id=source_job_candidate_id,
        created_by_sub=created_by_sub,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def ensure_initial_contract_document(
    db: Session,
    *,
    employee_id: str,
    created_by_sub: str,
) -> EmployeeDocument:
    _require_employee(db, employee_id)
    contract_sync = (
        db.query(OdooContractSync)
        .filter(OdooContractSync.employee_id == employee_id)
        .one_or_none()
    )
    if contract_sync is None:
        raise EmployeeDocumentValidationError(
            "No hay datos estructurados de contrato disponibles para este empleado."
        )

    existing = (
        db.query(EmployeeDocument)
        .filter(EmployeeDocument.contract_sync_id == contract_sync.id)
        .one_or_none()
    )
    if existing is not None:
        return existing

    return create_document(
        db,
        employee_id=employee_id,
        document_type="CONTRACT",
        title="Contrato laboral",
        created_by_sub=created_by_sub,
        contract_sync_id=contract_sync.id,
        source_job_candidate_id=contract_sync.source_job_candidate_id,
    )


def _validate_signed_pdf(file_bytes: bytes, *, max_upload_bytes: int) -> None:
    if not file_bytes:
        raise EmployeeDocumentValidationError("El PDF firmado está vacío.")
    if len(file_bytes) > max_upload_bytes:
        raise EmployeeDocumentValidationError(
            "El PDF firmado supera el tamaño máximo permitido."
        )
    if not file_bytes.startswith(b"%PDF-"):
        raise EmployeeDocumentValidationError("El archivo firmado no es un PDF válido.")

    try:
        pdf = fitz.open(stream=file_bytes, filetype="pdf")
        try:
            if pdf.page_count <= 0:
                raise EmployeeDocumentValidationError(
                    "El PDF firmado no contiene páginas."
                )
        finally:
            pdf.close()
    except EmployeeDocumentValidationError:
        raise
    except Exception as exc:
        raise EmployeeDocumentValidationError(
            "El archivo firmado no es un PDF legible."
        ) from exc


def append_signed_version(
    db: Session,
    *,
    employee_id: str,
    document_id: str,
    file_bytes: bytes,
    original_filename: str,
    uploaded_by_sub: str,
    signed_at: datetime | None,
    storage: EmployeeDocumentStorage,
) -> EmployeeDocumentVersion:
    _validate_signed_pdf(
        file_bytes,
        max_upload_bytes=storage.config.max_upload_bytes,
    )
    document = _require_document(
        db,
        employee_id=employee_id,
        document_id=document_id,
        for_update=True,
    )
    if document.status == "VOID":
        raise EmployeeDocumentStateError(
            "No se pueden agregar versiones a un documento anulado."
        )

    current_max = (
        db.query(func.max(EmployeeDocumentVersion.version_number))
        .filter(EmployeeDocumentVersion.document_id == document.id)
        .scalar()
        or 0
    )
    version_number = int(current_max) + 1
    version_id = str(uuid.uuid4())
    key = signed_version_key(
        employee_id,
        document.id,
        version_number,
        version_id,
    )
    normalized_filename = str(original_filename or "documento-firmado.pdf").strip()
    if not normalized_filename:
        normalized_filename = "documento-firmado.pdf"

    try:
        storage.put_bytes(key, file_bytes, "application/pdf")
    except Exception as exc:
        raise EmployeeDocumentStorageError(
            "No fue posible almacenar el PDF firmado."
        ) from exc

    now = datetime.now(timezone.utc)
    try:
        version = EmployeeDocumentVersion(
            id=version_id,
            document_id=document.id,
            version_number=version_number,
            storage_key=key,
            original_filename=normalized_filename,
            mime_type="application/pdf",
            file_size=len(file_bytes),
            sha256=hashlib.sha256(file_bytes).hexdigest(),
            signed_at=signed_at,
            uploaded_by_sub=uploaded_by_sub,
            uploaded_at=now,
            created_at=now,
        )
        db.add(version)
        db.flush()

        if document.current_signed_version_id:
            previous = (
                db.query(EmployeeDocumentVersion)
                .filter(
                    EmployeeDocumentVersion.id
                    == document.current_signed_version_id
                )
                .one_or_none()
            )
            if previous is not None:
                previous.superseded_at = now
                previous.superseded_by_version_id = version.id

        document.current_signed_version_id = version.id
        document.status = "SIGNED"
        db.commit()
        db.refresh(version)
        db.refresh(document)
        return version
    except Exception as exc:
        db.rollback()
        try:
            storage.delete_object(key)
        except Exception:
            pass
        if isinstance(exc, EmployeeDocumentStorageError):
            raise
        raise EmployeeDocumentStorageError(
            "No fue posible registrar la versión firmada."
        ) from exc


def void_document(
    db: Session,
    *,
    employee_id: str,
    document_id: str,
    reason: str,
    actor_sub: str,
) -> EmployeeDocument:
    document = _require_document(
        db,
        employee_id=employee_id,
        document_id=document_id,
        for_update=True,
    )
    normalized_reason = str(reason or "").strip()
    if not normalized_reason:
        raise EmployeeDocumentValidationError(
            "Debes indicar el motivo de anulación."
        )
    if document.status == "VOID":
        return document

    document.status = "VOID"
    document.void_reason = normalized_reason
    document.voided_by_sub = actor_sub
    document.voided_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(document)
    return document


def list_documents_for_hr(
    db: Session,
    *,
    employee_id: str,
) -> list[EmployeeDocument]:
    _require_employee(db, employee_id)
    return (
        db.query(EmployeeDocument)
        .filter(EmployeeDocument.employee_id == employee_id)
        .order_by(EmployeeDocument.created_at.desc(), EmployeeDocument.id.desc())
        .all()
    )


def list_current_signed_for_employee(
    db: Session,
    *,
    employee_id: str,
) -> list[EmployeeDocument]:
    _require_employee(db, employee_id)
    return (
        db.query(EmployeeDocument)
        .filter(
            EmployeeDocument.employee_id == employee_id,
            EmployeeDocument.status == "SIGNED",
            EmployeeDocument.current_signed_version_id.isnot(None),
        )
        .order_by(EmployeeDocument.created_at.desc(), EmployeeDocument.id.desc())
        .all()
    )


def _version_payload(version: EmployeeDocumentVersion | None) -> dict | None:
    if version is None:
        return None
    return {
        "id": version.id,
        "version_number": version.version_number,
        "original_filename": version.original_filename,
        "mime_type": version.mime_type,
        "file_size": version.file_size,
        "sha256": version.sha256,
        "signed_at": version.signed_at.isoformat() if version.signed_at else None,
        "uploaded_by_sub": version.uploaded_by_sub,
        "uploaded_at": (
            version.uploaded_at.isoformat() if version.uploaded_at else None
        ),
        "superseded_at": (
            version.superseded_at.isoformat()
            if version.superseded_at else None
        ),
        "superseded_by_version_id": version.superseded_by_version_id,
        "is_current": False,
    }


def _artifact_payload(artifact: EmployeeDocumentArtifact) -> dict:
    return {
        "id": artifact.id,
        "artifact_kind": artifact.artifact_kind,
        "mime_type": artifact.mime_type,
        "file_size": artifact.file_size,
        "sha256": artifact.sha256,
        "template_version": artifact.template_version,
        "created_at": artifact.created_at.isoformat() if artifact.created_at else None,
    }


def document_payload(
    document: EmployeeDocument,
    *,
    db: Session,
    include_history: bool = False,
    include_artifacts: bool = True,
) -> dict:
    current = None
    if document.current_signed_version_id:
        current = (
            db.query(EmployeeDocumentVersion)
            .filter(
                EmployeeDocumentVersion.id
                == document.current_signed_version_id
            )
            .one_or_none()
        )
    current_payload = _version_payload(current)
    if current_payload is not None:
        current_payload["is_current"] = True

    payload = {
        "id": document.id,
        "employee_id": document.employee_id,
        "document_type": document.document_type,
        "title": document.title,
        "status": document.status,
        "contract_sync_id": document.contract_sync_id,
        "source_job_candidate_id": document.source_job_candidate_id,
        "current_signed_version_id": document.current_signed_version_id,
        "current_signed_version": current_payload,
        "created_by_sub": document.created_by_sub,
        "voided_by_sub": document.voided_by_sub,
        "voided_at": (
            document.voided_at.isoformat() if document.voided_at else None
        ),
        "void_reason": document.void_reason,
        "created_at": document.created_at.isoformat() if document.created_at else None,
        "updated_at": document.updated_at.isoformat() if document.updated_at else None,
    }

    if include_artifacts:
        artifacts = (
            db.query(EmployeeDocumentArtifact)
            .filter(EmployeeDocumentArtifact.document_id == document.id)
            .order_by(EmployeeDocumentArtifact.created_at.desc())
            .all()
        )
        payload["artifacts"] = [_artifact_payload(item) for item in artifacts]

    if include_history:
        versions = (
            db.query(EmployeeDocumentVersion)
            .filter(EmployeeDocumentVersion.document_id == document.id)
            .order_by(
                EmployeeDocumentVersion.version_number.desc(),
                EmployeeDocumentVersion.created_at.desc(),
            )
            .all()
        )
        version_payloads = []
        for version in versions:
            item = _version_payload(version)
            item["is_current"] = version.id == document.current_signed_version_id
            version_payloads.append(item)
        payload["versions"] = version_payloads

    return payload
