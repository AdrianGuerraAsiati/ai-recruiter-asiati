"""HTTP routes for private employee intake submissions and review."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_current_principal, get_db, require_permission
from app.domains.employee_documents import notifications, service
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


@router.get("/review-queue")
def document_review_queue(
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("employee_documents.read_all")),
):
    return service.review_queue(db)


@router.post("/employees/{employee_id}/contract/upload", status_code=201)
def create_employee_contract_upload(
    employee_id: str,
    body: CreateEmployeeDocumentUploadRequest,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("employee_documents.review")),
):
    if body.document_type != "EMPLOYMENT_CONTRACT":
        raise HTTPException(status_code=422, detail="Solo se permite cargar el contrato laboral.")
    try:
        return service.create_upload(
            db, employee_id=employee_id, document_type=body.document_type,
            filename=body.filename, content_type=body.content_type,
            size_bytes=body.size_bytes, admin_upload=True,
        )
    except Exception as exc:
        _translate(exc)


@router.post("/employees/{employee_id}/contract/complete")
def complete_employee_contract_upload(
    employee_id: str,
    body: FinalizeEmployeeDocumentUploadRequest,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_permission("employee_documents.review")),
):
    if body.document_type != "EMPLOYMENT_CONTRACT":
        raise HTTPException(status_code=422, detail="Solo se permite cargar el contrato laboral.")
    try:
        service.finalize_upload(
            db, employee_id=employee_id, uploaded_by_sub=principal["sub"],
            document_type=body.document_type, filename=body.filename,
            key=body.key, content_type=body.content_type, size_bytes=body.size_bytes,
            admin_upload=True,
        )
        return service.portfolio_payload(db, employee_id, include_admin_only=True)
    except Exception as exc:
        _translate(exc)


@router.get("/employees/{employee_id}/welcome")
def employee_welcome_status(
    employee_id: str,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("employee_documents.read_all")),
):
    try:
        service.require_employee(db, employee_id)
        return notifications.status_for_employee(db, employee_id)
    except Exception as exc:
        _translate(exc)


@router.post("/employees/{employee_id}/welcome/retry")
def retry_employee_welcome(
    employee_id: str,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("employee_documents.review")),
):
    # Never send a congratulatory hiring notice to a mere applicant.
    from app.models import JobCandidate

    hired = (
        db.query(JobCandidate)
        .filter(
            JobCandidate.employee_id == employee_id,
            JobCandidate.application_status == "HIRED",
        )
        .first()
    )
    if hired is None:
        raise HTTPException(status_code=409, detail="Solo se notifica a empleados contratados.")
    try:
        service.require_employee(db, employee_id)
        return notifications.send_welcome(db, employee_id)
    except Exception as exc:
        _translate(exc)


@router.get("/employees/{employee_id}")
def employee_documents(
    employee_id: str,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("employee_documents.read_all")),
):
    try:
        return service.portfolio_payload(db, employee_id, include_admin_only=True)
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
        if document.document_type == "EMPLOYMENT_CONTRACT" and not can_read_all:
            raise HTTPException(status_code=403, detail="El contrato laboral solo puede consultarlo Talento Humano.")
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
