"""HTTP routes for private employee intake submissions and review."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_current_principal, get_db, require_permission
from app.domains.employee_documents import service
from app.domains.employee_documents.schemas import (
    CreateEmployeeDocumentUploadRequest,
    FinalizeEmployeeDocumentUploadRequest,
    ReviewEmployeeDocumentRequest,
    SaveEmployeeDocumentValueRequest,
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
        return service.portfolio_payload(db, principal["profile"]["id"])
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
        service.finalize_upload(
            db,
            employee_id=principal["profile"]["id"],
            uploaded_by_sub=principal["sub"],
            document_type=body.document_type,
            filename=body.filename,
            key=body.key,
            content_type=body.content_type,
            size_bytes=body.size_bytes,
        )
        return service.portfolio_payload(db, principal["profile"]["id"])
    except Exception as exc:
        _translate(exc)


@router.put("/me/value")
def save_my_document_value(
    body: SaveEmployeeDocumentValueRequest,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_permission("employee_documents.upload_own")),
):
    try:
        service.save_value(
            db,
            employee_id=principal["profile"]["id"],
            uploaded_by_sub=principal["sub"],
            document_type=body.document_type,
            value=body.value,
        )
        return service.portfolio_payload(db, principal["profile"]["id"])
    except Exception as exc:
        _translate(exc)


@router.get("/employees/{employee_id}")
def employee_documents(
    employee_id: str,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("employee_documents.read_all")),
):
    try:
        return service.portfolio_payload(db, employee_id)
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


@router.post("/{document_id}/review")
def review_document(
    document_id: str,
    body: ReviewEmployeeDocumentRequest,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_permission("employee_documents.review")),
):
    try:
        document = service.review_document(
            db,
            document_id=document_id,
            status=body.status,
            comment=body.comment,
            reviewed_by_sub=principal["sub"],
        )
        return service.portfolio_payload(db, document.employee_id)
    except Exception as exc:
        _translate(exc)
