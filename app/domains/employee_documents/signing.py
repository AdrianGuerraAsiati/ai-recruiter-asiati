"""Prepare reviewed employment-contract PDFs as editable Odoo Sign templates.

SAFE FIRST PHASE: staging only; this module DOES NOT issue signature requests,
create signers, send email, or mark a contract as signed.
"""
from __future__ import annotations

import base64
import os
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.domains.employee_documents import service
from app.domains.employee_documents.models import EmployeeDocument
from app.domains.odoo_sync import staging
from app.infrastructure.storage import employee_documents as storage
from app.integrations.odoo.client import OdooClientError


class SignUnavailable(RuntimeError):
    pass


class SignNotReady(ValueError):
    pass


def staging_enabled() -> bool:
    return os.getenv("ODOO_SIGN_STAGING_PREPARE_ENABLED", "").strip().lower() in (
        "1", "true", "yes"
    )


def _test_employee_allowed(employee_id: str) -> bool:
    """Explicit fixture allowlist prevents copying real contracts into staging."""
    allowed = {
        value.strip()
        for value in os.getenv("ODOO_SIGN_TEST_EMPLOYEE_IDS", "").split(",")
        if value.strip()
    }
    return employee_id in allowed


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
    base_url = staging.staging_settings().base_url
    return f"{base_url}/web#id={int(template_id)}&model=sign.template&view_type=form"


def readiness(db: Session, employee_id: str, *, client=None) -> dict:
    document = _contract(db, employee_id)
    state = document.odoo_sign_status if document is not None else "NOT_PREPARED"
    result = {
        "enabled": staging_enabled(),
        "ready": False,
        "status": state,
        "template_url": None,
        "message": "",
        "staging_only": True,
    }
    if document and state == "PREPARED" and document.odoo_sign_template_id:
        try:
            result["template_url"] = _url(document.odoo_sign_template_id)
        except (ValueError, staging.OdooNotConfigured):
            pass
        result["message"] = "Plantilla preparada. Abre Odoo staging, ubica las firmas y envía desde Odoo."
        return result
    if not staging_enabled():
        result["message"] = "La preparación de Odoo Sign en staging aún no está habilitada."
        return result
    if not _test_employee_allowed(employee_id):
        result["message"] = "Solo empleados de prueba autorizados pueden preparar contratos en staging."
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
        target = client or staging.build_staging_client()
        template_fields = target.fields_get("sign.template")
        attachment_fields = target.fields_get("ir.attachment")
        # Discover actual capabilities before ever trying a write.
        if not {"attachment_id"}.issubset(template_fields) or not {"datas", "mimetype"}.issubset(attachment_fields):
            raise SignUnavailable("El esquema de Odoo Sign no permite preparar plantillas desde PDF.")
    except (OdooClientError, staging.OdooNotConfigured, SignUnavailable):
        result["message"] = "Odoo Sign no está disponible o el usuario técnico no tiene los permisos requeridos."
        return result
    result["ready"] = True
    result["message"] = "Odoo Sign staging disponible. Preparar no envía solicitudes ni correos."
    return result


def prepare(db: Session, employee_id: str, *, client=None) -> dict:
    """Idempotently create an Odoo Sign template, not a signature request."""
    if not staging_enabled():
        raise SignUnavailable("La preparación de Odoo Sign en staging está deshabilitada.")
    if not _test_employee_allowed(employee_id):
        raise SignUnavailable("Este empleado no está autorizado para la prueba de Odoo Sign staging.")

    document = _contract(db, employee_id, lock=True)
    if document is None or not document.storage_key:
        raise SignNotReady("Primero debes cargar el contrato laboral.")
    if document.odoo_sign_status == "PREPARED" and document.odoo_sign_template_id:
        return readiness(db, employee_id, client=client)
    if document.odoo_sign_status == "PREPARING":
        raise SignNotReady("La preparación ya está en curso.")
    if document.review_status != "APPROVED":
        raise SignNotReady("El contrato debe estar aprobado por Talento Humano.")
    if document.content_type != "application/pdf" or not str(document.original_filename or "").lower().endswith(".pdf"):
        raise SignNotReady("Solo se pueden preparar contratos en PDF.")

    # Readiness checks against the actual staging schema; fail closed.
    capabilities = readiness(db, employee_id, client=client)
    if not capabilities["ready"]:
        raise SignUnavailable(capabilities["message"])

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
        target = client or staging.build_staging_client()
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
                pass  # Inspect orphan attachments in staging during E2E testing.
        document = _contract(db, employee_id)
        if document and document.odoo_sign_status == "PREPARING":
            document.odoo_sign_status = "FAILED"
            db.commit()
        # Never expose remote credentials, SQL errors or document contents.
        raise SignUnavailable("No se pudo preparar el contrato en Odoo staging. Revisa los registros del servidor.") from exc
    return readiness(db, employee_id, client=client)
