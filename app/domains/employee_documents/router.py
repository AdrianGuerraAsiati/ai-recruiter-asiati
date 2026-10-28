"""HTTP routes for private employee intake submissions and review."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_current_principal, get_db, require_permission
from app.domains.employee_documents import notifications, service, signing, sign_requests, signed_artifacts, sign_dispatch, sign_send, sign_fields
from app.domains.employee_documents.schemas import (
    ConfirmContractSignPreparation,
    LinkStagingSignRequest,
    PreviewOdooSignRequest,
    SendOdooSignRequest,
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


@router.get("/applications")
def applicant_document_options(
    q: str = "",
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("employee_documents.read_all")),
):
    return service.application_select_options(db, query=q)


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



@router.get("/employees/{employee_id}/contract/sign")
def employee_contract_sign_status(
    employee_id: str,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("employee_documents.read_all")),
):
    try:
        return signing.readiness(db, employee_id)
    except Exception as exc:
        _translate(exc)


@router.post("/employees/{employee_id}/contract/sign/prepare")
def prepare_employee_contract_in_odoo_sign(
    employee_id: str,
    body: ConfirmContractSignPreparation,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("employee_documents.review")),
):
    if not body.confirm:
        raise HTTPException(status_code=422, detail="Confirma la preparación del contrato.")
    try:
        return signing.prepare(db, employee_id)
    except signing.SignNotReady as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except signing.SignUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        _translate(exc)



@router.get("/employees/{employee_id}/contract/sign/fields")
def preview_automatic_signature_fields(
    employee_id: str,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("employee_documents.review")),
):
    """Read-only positioning preview derived from the approved demo PDF."""
    try:
        return sign_fields.preview(db, employee_id)
    except sign_fields.SignFieldsNotReady as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except sign_fields.SignFieldsUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        _translate(exc)


@router.post("/employees/{employee_id}/contract/sign/fields")
def apply_automatic_signature_fields(
    employee_id: str,
    body: ConfirmContractSignPreparation,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("employee_documents.review")),
):
    """Place mandatory fields; no signature requests, Odoo mail or user creation."""
    try:
        return sign_fields.apply(db, employee_id)
    except sign_fields.SignFieldsNotReady as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except sign_fields.SignFieldsUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        _translate(exc)


@router.get("/employees/{employee_id}/contract/sign/request")
def get_staging_sign_request(
    employee_id: str,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("employee_documents.read_all")),
):
    try:
        return sign_requests.local_status(db, employee_id)
    except Exception as exc:
        _translate(exc)


@router.post("/employees/{employee_id}/contract/sign/request/automatic-preview")
def preview_auto_staged_sign_request(
    employee_id: str,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("employee_documents.review")),
):
    """Resolve both synthetic Odoo contacts server-side; never expose IDs."""
    try:
        return sign_dispatch.preview_automatic(db, employee_id)
    except sign_dispatch.DispatchNotReady as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (sign_dispatch.DispatchUnavailable,
            sign_requests.SignTrackingUnavailable) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        _translate(exc)


@router.post("/employees/{employee_id}/contract/sign/request/automatic-send")
def send_auto_staged_sign_request(
    employee_id: str,
    body: ConfirmContractSignPreparation,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("employee_documents.review")),
):
    """Explicit one-time request; IDs linked automatically by the backend."""
    try:
        return sign_send.send_automatic(db, employee_id)
    except (sign_send.DispatchConflict, sign_dispatch.DispatchNotReady) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (sign_send.DispatchOutcomeUnknown, sign_dispatch.DispatchUnavailable,
            sign_requests.SignTrackingUnavailable) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        _translate(exc)


@router.post("/employees/{employee_id}/contract/sign/request/preview")
def preview_staging_sign_request(
    employee_id: str,
    body: PreviewOdooSignRequest,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("employee_documents.review")),
):
    """Read-only: validate the two Odoo Sign wizard recipients; never send mail."""
    try:
        return sign_dispatch.preview(
            db, employee_id,
            employee_partner_id=body.employee_partner_id,
            representative_partner_id=body.representative_partner_id,
        )
    except sign_dispatch.DispatchNotReady as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (sign_dispatch.DispatchUnavailable,
            sign_requests.SignTrackingUnavailable) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        _translate(exc)


@router.get("/employees/{employee_id}/contract/sign/request/send-status")
def staged_sign_dispatch_status(
    employee_id: str,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("employee_documents.read_all")),
):
    from app.domains.employee_documents import signing
    try:
        document = signing._contract(db, employee_id)
        return {
            "staging_only": False,
            "enabled": sign_dispatch.sending_enabled(),
            "status": document.odoo_sign_dispatch_status if document else "NOT_SENT",
            "request_id": document.odoo_sign_request_id if document else None,
        }
    except Exception as exc:
        _translate(exc)


@router.post("/employees/{employee_id}/contract/sign/request/send")
def send_staged_sign_request(
    employee_id: str,
    body: SendOdooSignRequest,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("employee_documents.review")),
):
    try:
        return sign_send.send(
            db, employee_id,
            employee_partner_id=body.employee_partner_id,
            representative_partner_id=body.representative_partner_id,
        )
    except (sign_send.DispatchConflict, sign_dispatch.DispatchNotReady) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (sign_send.DispatchOutcomeUnknown, sign_dispatch.DispatchUnavailable,
            sign_requests.SignTrackingUnavailable) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        _translate(exc)


@router.post("/employees/{employee_id}/contract/sign/request/reconcile")
def reconcile_staged_sign_request(
    employee_id: str,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("employee_documents.review")),
):
    try:
        return sign_send.reconcile(db, employee_id)
    except sign_send.DispatchConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (sign_send.DispatchOutcomeUnknown, sign_requests.SignTrackingUnavailable,
            sign_dispatch.DispatchUnavailable) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        _translate(exc)


@router.post("/employees/{employee_id}/contract/sign/request/link")
def link_staging_sign_request(
    employee_id: str,
    body: LinkStagingSignRequest,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("employee_documents.review")),
):
    try:
        return sign_requests.track(db, employee_id, request_id=body.request_id)
    except sign_requests.SignTrackingConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except sign_requests.SignTrackingUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        _translate(exc)


@router.post("/employees/{employee_id}/contract/sign/request/refresh")
def refresh_staging_sign_request(
    employee_id: str,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("employee_documents.review")),
):
    try:
        return sign_requests.track(db, employee_id)
    except sign_requests.SignTrackingConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except sign_requests.SignTrackingUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        _translate(exc)


@router.get("/employees/{employee_id}/contract/signed")
def signed_contract_status(
    employee_id: str,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("employee_documents.read_all")),
):
    try:
        return signed_artifacts.status(db, employee_id)
    except Exception as exc:
        _translate(exc)


@router.post("/employees/{employee_id}/contract/signed/archive")
def archive_signed_contract(
    employee_id: str,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("employee_documents.review")),
):
    try:
        return signed_artifacts.archive(db, employee_id)
    except signed_artifacts.ArchiveNotReady as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except signed_artifacts.ArchiveUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        _translate(exc)


@router.get("/employees/{employee_id}/contract/signed/download")
def download_signed_contract_as_hr(
    employee_id: str,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("employee_documents.read_all")),
):
    try:
        return signed_artifacts.download(db, employee_id)
    except signed_artifacts.ArchiveNotReady as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        _translate(exc)


@router.get("/employees/{employee_id}/contract/signed/certificate/download")
def download_signed_certificate_as_hr(
    employee_id: str,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("employee_documents.read_all")),
):
    try:
        return signed_artifacts.download_certificate(db, employee_id)
    except signed_artifacts.ArchiveNotReady as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        _translate(exc)


@router.get("/me/contract/signed/certificate/download")
def download_own_signed_certificate(
    db: Session = Depends(get_db),
    principal: dict = Depends(require_permission("employee_documents.read_own")),
):
    try:
        return signed_artifacts.download_certificate(db, principal["profile"]["id"])
    except signed_artifacts.ArchiveNotReady as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        _translate(exc)


@router.get("/me/contract/signed")
def own_signed_contract_status(
    db: Session = Depends(get_db),
    principal: dict = Depends(require_permission("employee_documents.read_own")),
):
    try:
        return signed_artifacts.status(db, principal["profile"]["id"])
    except Exception as exc:
        _translate(exc)


@router.get("/me/contract/signed/download")
def download_own_signed_contract(
    db: Session = Depends(get_db),
    principal: dict = Depends(require_permission("employee_documents.read_own")),
):
    try:
        return signed_artifacts.download(db, principal["profile"]["id"])
    except signed_artifacts.ArchiveNotReady as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
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
        return service.portfolio_payload(db, document.employee_id, include_admin_only=True)
    except Exception as exc:
        _translate(exc)
