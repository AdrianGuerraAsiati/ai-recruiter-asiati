"""HTTP routes for private employee documents."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_current_principal, get_db, require_permission
from app.domains.employee_documents import service
from app.domains.employee_documents.schemas import (
    CreateEmployeeDocumentUploadRequest,
    FinalizeEmployeeDocumentUploadRequest,
)

router = APIRouter(prefix="/api/employee-documents", tags=["employee-documents"])


def _translate(exc: Exception):
    if isinstance(exc, service.EmployeeNotFound):
        raise HTTPException(status_code=404, detail="Empleado no encontrado.") from exc
    if isinstance(exc, service.EmployeeDocumentNotFound):
        raise HTTPException(status_code=404, detail="Documento no encontrado.") from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    raise exc


@router.get("/me")
def my_documents(
    db: Session = Depends(get_db),
    principal: dict = Depends(require_permission("employee_documents.read_own")),
):
    try:
        items = service.list_documents(db, principal["profile"]["id"])
        return {"items": items, "total": len(items)}
    except Exception as exc:
        _translate(exc)


@router.post("/me/upload", status_code=201)
def create_my_document_upload(
    body: CreateEmployeeDocumentUploadRequest,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_permission("employee_documents.upload_own")),
):
    try:
        return service.create_upload(
            db,
            employee_id=principal["profile"]["id"],
            document_type=body.document_type,
            filename=body.filename,
            content_type=body.content_type,
            size_bytes=body.size_bytes,
        )
    except Exception as exc:
        _translate(exc)


@router.post("/me/complete")
def complete_my_document_upload(
    body: FinalizeEmployeeDocumentUploadRequest,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_permission("employee_documents.upload_own")),
):
    try:
        document = service.finalize_upload(
            db,
            employee_id=principal["profile"]["id"],
            uploaded_by_sub=principal["sub"],
            document_type=body.document_type,
            filename=body.filename,
            key=body.key,
            content_type=body.content_type,
            size_bytes=body.size_bytes,
        )
        return service.document_payload(document)
    except Exception as exc:
        _translate(exc)


@router.get("/employees/{employee_id}")
def employee_documents(
    employee_id: str,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("employee_documents.read_all")),
):
    try:
        items = service.list_documents(db, employee_id)
        return {"items": items, "total": len(items)}
    except Exception as exc:
        _translate(exc)


@router.get("/{document_id}/download")
def download_document(
    document_id: str,
    db: Session = Depends(get_db),
    principal: dict = Depends(get_current_principal),
):
    try:
        document = service.require_document(db, document_id)
        own_document = document.employee_id == principal["profile"]["id"]
        can_read_all = "employee_documents.read_all" in set(principal.get("permissions") or [])
        if not own_document and not can_read_all:
            raise HTTPException(status_code=403, detail="No puedes consultar este documento.")
        return service.download_payload(db, document_id)
    except HTTPException:
        raise
    except Exception as exc:
        _translate(exc)
