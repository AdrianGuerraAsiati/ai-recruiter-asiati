"""Employee self-service and requested-document HTTP routes."""

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.deps import get_db, require_permission
from app.domains.employee_documents import service
from app.domains.employee_documents.schemas import (
    CreateDocumentRequest,
    UpdateOwnProfileRequest,
)


self_router = APIRouter(prefix="/api/employee-self", tags=["employee-self"])
admin_router = APIRouter(prefix="/api/employees", tags=["employee-documents"])


def _employee_id(principal: dict) -> str:
    employee_id = str((principal.get("profile") or {}).get("id") or "").strip()
    if not employee_id:
        raise HTTPException(status_code=403, detail="Perfil de empleado no disponible.")
    return employee_id


def _download_response(payload: bytes, filename: str, content_type: str) -> Response:
    encoded = quote(filename)
    return Response(
        content=payload,
        media_type=content_type,
        headers={
            "Content-Disposition": (
                f"attachment; filename*=UTF-8''{encoded}"
            ),
            "Cache-Control": "private, no-store",
        },
    )


@self_router.get("/profile")
def get_own_profile(
    db: Session = Depends(get_db),
    principal: dict = Depends(require_permission("profile.read_own")),
):
    try:
        return service.own_profile_payload(db, _employee_id(principal))
    except service.EmployeeDocumentNotFound as exc:
        raise HTTPException(status_code=404, detail="Empleado no encontrado.") from exc


@self_router.put("/profile")
def update_own_profile(
    body: UpdateOwnProfileRequest,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_permission("profile.update_own")),
):
    try:
        return service.update_own_profile(
            db,
            employee_id=_employee_id(principal),
            changes=body.model_dump(exclude_unset=True),
            actor_sub=str(principal.get("sub") or ""),
        )
    except service.EmployeeDocumentNotFound as exc:
        raise HTTPException(status_code=404, detail="Empleado no encontrado.") from exc


@self_router.get("/documents")
def list_own_documents(
    db: Session = Depends(get_db),
    principal: dict = Depends(require_permission("employee_documents.read_own")),
):
    employee_id = _employee_id(principal)
    return {"items": service.list_document_requests(db, employee_id)}


@self_router.post("/documents/{request_id}/upload")
async def upload_own_document(
    request_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    principal: dict = Depends(require_permission("employee_documents.upload_own")),
):
    payload = await file.read(service.MAX_DOCUMENT_BYTES + 1)
    try:
        return service.upload_document(
            db,
            employee_id=_employee_id(principal),
            request_id=request_id,
            filename=file.filename or "document",
            content_type=file.content_type or "application/octet-stream",
            payload=payload,
            actor_sub=str(principal.get("sub") or ""),
        )
    except service.EmployeeDocumentNotFound as exc:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada.") from exc
    except service.EmployeeSelfServiceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@self_router.get("/documents/{request_id}/download")
def download_own_document(
    request_id: str,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_permission("employee_documents.read_own")),
):
    try:
        payload, filename, content_type = service.download_document(
            db,
            employee_id=_employee_id(principal),
            request_id=request_id,
        )
    except service.EmployeeDocumentNotFound as exc:
        raise HTTPException(status_code=404, detail="Documento no encontrado.") from exc
    return _download_response(payload, filename, content_type)


@admin_router.get("/{employee_id}/documents")
def list_employee_documents(
    employee_id: str,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("employee_documents.read_all")),
):
    try:
        return {"items": service.list_document_requests(db, employee_id)}
    except service.EmployeeDocumentNotFound as exc:
        raise HTTPException(status_code=404, detail="Empleado no encontrado.") from exc


@admin_router.post("/{employee_id}/documents/requests", status_code=201)
def request_employee_document(
    employee_id: str,
    body: CreateDocumentRequest,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_permission("employee_documents.manage")),
):
    try:
        return service.create_document_request(
            db,
            employee_id=employee_id,
            label=body.label,
            document_type=body.document_type,
            required=body.required,
            requested_by_sub=str(principal.get("sub") or ""),
        )
    except service.EmployeeDocumentNotFound as exc:
        raise HTTPException(status_code=404, detail="Empleado no encontrado.") from exc


@admin_router.get("/{employee_id}/documents/{request_id}/download")
def download_employee_document(
    employee_id: str,
    request_id: str,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("employee_documents.read_all")),
):
    try:
        payload, filename, content_type = service.download_document(
            db,
            employee_id=employee_id,
            request_id=request_id,
        )
    except service.EmployeeDocumentNotFound as exc:
        raise HTTPException(status_code=404, detail="Documento no encontrado.") from exc
    return _download_response(payload, filename, content_type)
