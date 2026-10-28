"""Prepare reviewed employment-contract PDFs as editable Odoo Sign templates.

Creates only approved templates; the request dispatch is a separate action.
create signers, send email, or mark a contract as signed.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.domains.employee_documents import service
from app.domains.employee_documents.models import ApplicationContract, EmployeeDocument
from app.domains.hiring import application_contracts
from app.models import JobCandidate
from app.domains.employee_documents import sign_runtime
from app.infrastructure.storage import employee_documents as storage
from app.integrations.odoo.client import OdooClientError


class SignUnavailable(RuntimeError):
    pass


class SignNotReady(ValueError):
    pass


def production_enabled() -> bool:
    return sign_runtime.enabled()


def _contract(db: Session, employee_id: str, *, lock: bool = False) -> EmployeeDocument | None:
    service.require_employee(db, employee_id)
    query = db.query(EmployeeDocument).filter(
        EmployeeDocument.employee_id == employee_id,
        EmployeeDocument.document_type == "EMPLOYMENT_CONTRACT",
    )
    if lock:
        query = query.with_for_update()
    return query.one_or_none()


def _url(template_id: int) -> str:
    base_url = sign_runtime.base_url()
    return f"{base_url}/web#id={int(template_id)}&model=sign.template&view_type=form"



def _application_binding_matches(db: Session, document: EmployeeDocument) -> bool:
    binding = db.query(ApplicationContract).filter(
        ApplicationContract.document_id == document.id,
    ).one_or_none()
    if (
        binding is None
        or binding.employee_id != document.employee_id
        or not binding.source_storage_key
        or binding.source_storage_key != document.storage_key
        or document.content_type != "application/pdf"
        or not str(document.original_filename or "").lower().endswith(".pdf")
        or binding.odoo_company_id <= 0
    ):
        return False
    application = db.query(JobCandidate).filter(
        JobCandidate.id == binding.application_id,
    ).one_or_none()
    return bool(application and application.employee_id == document.employee_id)

def readiness(db: Session, employee_id: str, *, client=None) -> dict:
    document = _contract(db, employee_id)
    state = document.odoo_sign_status if document is not None else "NOT_PREPARED"
    result = {
        "enabled": production_enabled(),
        "ready": False,
        "status": state,
        "template_url": None,
        "message": "",
        "staging_only": False,
    }
    if document:
        if not document.storage_key:
            result["message"] = "Talento Humano debe cargar primero el contrato."
            return result
        if document.review_status != "APPROVED":
            result["message"] = "El contrato debe estar aprobado antes de preparar la firma."
            return result
        if document.content_type != "application/pdf" or not str(document.original_filename or "").lower().endswith(".pdf"):
            result["message"] = "Odoo Sign requiere un contrato en PDF."
            return result
        if not _application_binding_matches(db, document):
            result["status"] = "APPLICATION_CONTRACT_BINDING_REQUIRED"
            result["message"] = (
                "Antes de preparar Odoo Sign, vincula el contrato aprobado con la postulación "
                "y la empresa Odoo desde Postulaciones."
            )
            return result
    if document and document.odoo_sign_template_id:
        try:
            sign_runtime.assert_origin(document)
        except sign_runtime.ProductionSignUnavailable:
            result["message"] = "El contrato fue preparado en Odoo Test; no puede reutilizarse en producción."
            result["status"] = "CONTRACT_FROM_TEST"
            return result
    if document and state == "PREPARED" and document.odoo_sign_template_id:
        try:
            result["template_url"] = _url(document.odoo_sign_template_id)
        except (ValueError, sign_runtime.ProductionSignUnavailable):
            pass
        result["message"] = "Plantilla preparada. Abre Odoo Producción, ubica las firmas y envía desde Odoo."
        return result
    if not production_enabled():
        result["message"] = "La preparación de Odoo Sign en producción aún no está habilitada."
        return result
    if not document or not document.storage_key:
        result["message"] = "Talento Humano debe cargar primero el contrato."
        return result
    if document.review_status != "APPROVED":
        result["message"] = "El contrato debe estar aprobado antes de preparar la firma."
        return result
    if document.content_type != "application/pdf" or not str(document.original_filename or "").lower().endswith(".pdf"):
        result["message"] = "Odoo Sign requiere un contrato en PDF."
        return result
    if state == "PREPARING":
        result["message"] = "El contrato ya está siendo preparado. Vuelve a consultar su estado."
        return result
    try:
        target = client or sign_runtime.client()
        template_fields = target.fields_get("sign.template")
        attachment_fields = target.fields_get("ir.attachment")
        # Discover actual capabilities before ever trying a write.
        if not {"attachment_id"}.issubset(template_fields) or not {"datas", "mimetype"}.issubset(attachment_fields):
            raise SignUnavailable("El esquema de Odoo Sign no permite preparar plantillas desde PDF.")
    except (OdooClientError, sign_runtime.ProductionSignUnavailable, SignUnavailable):
        result["message"] = "Odoo Sign no está disponible o el usuario técnico no tiene los permisos requeridos."
        return result
    result["ready"] = True
    result["message"] = "Odoo Sign producción disponible. Preparar no envía solicitudes ni correos."
    return result


def prepare(db: Session, employee_id: str, *, client=None) -> dict:
    """Idempotently create an Odoo Sign template, not a signature request."""
    if not production_enabled():
        raise SignUnavailable("La preparación de Odoo Sign en producción está deshabilitada.")

    document = _contract(db, employee_id, lock=True)
    if document is None or not document.storage_key:
        raise SignNotReady("Primero debes cargar el contrato laboral.")
    try:
        sign_runtime.assert_origin(document, new=True)
    except sign_runtime.ProductionSignUnavailable as exc:
        raise SignNotReady(str(exc)) from exc
    if document.review_status != "APPROVED":
        raise SignNotReady("El contrato debe estar aprobado por Talento Humano.")
    if document.content_type != "application/pdf" or not str(document.original_filename or "").lower().endswith(".pdf"):
        raise SignNotReady("Solo se pueden preparar contratos en PDF.")
    if not _application_binding_matches(db, document):
        raise SignNotReady(
            "Antes de preparar Odoo Sign, vincula el contrato aprobado con la postulación y la empresa Odoo desde Postulaciones."
        )
    if document.odoo_sign_status == "PREPARED" and document.odoo_sign_template_id:
        return readiness(db, employee_id, client=client)
    if document.odoo_sign_status == "PREPARING":
        raise SignNotReady("La preparación ya está en curso.")

    # Readiness checks against the actual production schema; fail closed.
    capabilities = readiness(db, employee_id, client=client)
    if not capabilities["ready"]:
        raise SignUnavailable(capabilities["message"])

    document.odoo_sign_environment = "production"
    document.odoo_sign_status = "PREPARING"
    db.commit()
    attachment_id = None
    template_id = None
    try:
        pdf = storage.read_employee_pdf_for_signing(
            employee_id=employee_id,
            key=document.storage_key,
            expected_bytes=document.size_bytes,
        )
        target = client or sign_runtime.client()
        attachment_id = target.create("ir.attachment", {
            "name": document.original_filename,
            "type": "binary",
            "mimetype": "application/pdf",
            "datas": base64.b64encode(pdf).decode("ascii"),
        })
        fields = target.fields_get("sign.template")
        values = {"attachment_id": attachment_id}
        if "name" in fields:
            values["name"] = f"Contrato laboral - {employee_id}"
        template_id = target.create("sign.template", values)
        document.odoo_sign_template_id = template_id
        document.odoo_sign_attachment_id = attachment_id
        document.odoo_sign_source_key = document.storage_key
        document.odoo_sign_prepared_at = datetime.now(timezone.utc)
        document.odoo_sign_status = "PREPARED"
        db.commit()
    except Exception as exc:
        db.rollback()
        if attachment_id and not template_id:
            try:
                target.unlink("ir.attachment", [attachment_id])
            except Exception:
                pass  # Inspect orphan attachments in production after a failed remote call.
        document = _contract(db, employee_id)
        if document and document.odoo_sign_status == "PREPARING":
            document.odoo_sign_status = "FAILED"
            db.commit()
        # Never expose remote credentials, SQL errors or document contents.
        raise SignUnavailable("No se pudo preparar el contrato en Odoo Producción. Revisa los registros del servidor.") from exc
    return readiness(db, employee_id, client=client)
