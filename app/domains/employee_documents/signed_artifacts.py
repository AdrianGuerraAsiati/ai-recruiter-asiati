"""Safely archive signed PDFs from a verified Odoo Sign staging request.

No Odoo writes or emails. Requires explicit staging fixture allowlists and a
schema-verified signed attachment relation; original contract is immutable.
"""
from __future__ import annotations

import base64
import binascii
import os
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.domains.employee_documents import sign_requests, signing
from app.domains.odoo_sync import staging
from app.infrastructure.storage import employee_documents as storage
from app.integrations.odoo.client import OdooClientError


class ArchiveNotReady(ValueError):
    pass


class ArchiveUnavailable(RuntimeError):
    pass


# The actual Enterprise v18 field MUST be established in Odoo staging before
# enabling. Only explicit final-document relation fields are acceptable.
SIGNED_ATTACHMENT_FIELDS = frozenset({
    "completed_document_attachment_ids",
    "completed_document_attachment_id",
    "signed_document_attachment_id",
    "signed_document_attachment_ids",
})


def archive_enabled() -> bool:
    return os.getenv("ODOO_SIGN_STAGING_ARCHIVE_ENABLED", "").strip().lower() in (
        "1", "true", "yes"
    )


def signed_artifact_field() -> str:
    field = os.getenv("ODOO_SIGN_STAGING_SIGNED_ATTACHMENT_FIELD", "").strip()
    if field not in SIGNED_ATTACHMENT_FIELDS:
        raise ArchiveUnavailable(
            "El campo de adjunto firmado debe validarse en Odoo staging antes de habilitar la copia."
        )
    return field


def status(db: Session, employee_id: str) -> dict:
    document = signing._contract(db, employee_id)
    if not document or not document.odoo_sign_signed_storage_key:
        return {"archived": False, "archived_at": None, "sha256": None,
                "staging_only": True}
    return {
        "archived": True,
        "archived_at": (
            document.odoo_sign_signed_at.isoformat()
            if document.odoo_sign_signed_at else None
        ),
        "sha256": document.odoo_sign_signed_sha256,
        "staging_only": True,
    }


def _signed_attachment(target, *, request_id: int, field_name: str) -> tuple[int, bytes]:
    request_fields = target.fields_get("sign.request")
    remote_field = request_fields.get(field_name)
    if not isinstance(remote_field, dict) or remote_field.get("type") not in (
        "many2one", "many2many",
    ) or remote_field.get("relation") != "ir.attachment":
        raise ArchiveUnavailable("Odoo Sign no expone un campo validado para el PDF firmado.")
    rows = target.search_read(
        "sign.request", [("id", "=", request_id)], fields=["id", field_name], limit=1,
    )
    if len(rows) != 1 or rows[0].get("id") != request_id:
        raise ArchiveNotReady("La solicitud firmada no se encuentra disponible.")
    value = rows[0].get(field_name)
    if remote_field["type"] == "many2one":
        attachment_id = sign_requests._m2o_id(value)
        ids = [attachment_id] if attachment_id else []
    else:
        ids = value if isinstance(value, list) else []
    if len(ids) != 1 or type(ids[0]) is not int or ids[0] <= 0:
        raise ArchiveNotReady("Se esperaba exactamente un PDF firmado para esta solicitud.")

    fields = target.fields_get("ir.attachment")
    mandatory = {"id", "datas", "mimetype", "name"}
    if not mandatory.issubset(fields):
        raise ArchiveUnavailable("Odoo no permite leer el PDF firmado con el usuario técnico.")
    selected = sorted(mandatory | ({"file_size"} if "file_size" in fields else set()))
    attachments = target.search_read(
        "ir.attachment", [("id", "=", ids[0])], fields=selected, limit=1,
    )
    if len(attachments) != 1 or attachments[0].get("id") != ids[0]:
        raise ArchiveNotReady("El adjunto del contrato firmado no está disponible.")
    item = attachments[0]
    if str(item.get("mimetype") or "").casefold() != "application/pdf":
        raise ArchiveNotReady("El documento terminado de Odoo no es PDF.")
    encoded = item.get("datas")
    if not isinstance(encoded, str) or len(encoded) > (
        ((storage.MAX_EMPLOYEE_DOCUMENT_BYTES + 2) // 3) * 4 + 8
    ):
        raise ArchiveNotReady("El PDF firmado no está disponible o excede 15 MB.")
    try:
        pdf = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ArchiveNotReady("El adjunto de Odoo no contiene un PDF íntegro.") from exc
    if item.get("file_size") not in (None, False) and int(item["file_size"]) != len(pdf):
        raise ArchiveNotReady("El tamaño del adjunto firmado no coincide.")
    if not 100 <= len(pdf) <= storage.MAX_EMPLOYEE_DOCUMENT_BYTES:
        raise ArchiveNotReady("PDF firmado fuera del límite de 15 MB.")
    if not pdf.startswith(b"%PDF-") or b"%%EOF" not in pdf[-2048:]:
        raise ArchiveNotReady("El adjunto de Odoo no es un PDF completo.")
    return ids[0], pdf


def archive(db: Session, employee_id: str, *, client=None) -> dict:
    if not archive_enabled():
        raise ArchiveUnavailable("La copia de contratos firmados desde staging está deshabilitada.")
    sign_requests._require_fixture(employee_id)
    field_name = signed_artifact_field()

    document = signing._contract(db, employee_id)
    if document is None or document.odoo_sign_request_id is None:
        raise ArchiveNotReady("Debes vincular primero la solicitud de firma del contrato de prueba.")
    if document.odoo_sign_signed_storage_key:
        return status(db, employee_id)

    try:
        target = client or staging.build_staging_client()
        refreshed = sign_requests.track(db, employee_id, client=target)
        if refreshed["status"] != "SIGNED":
            raise ArchiveNotReady("Ambos firmantes deben completar la firma antes de archivar.")
        document = signing._contract(db, employee_id, lock=True)
        if document.odoo_sign_signed_storage_key:
            return status(db, employee_id)
        attachment_id, pdf = _signed_attachment(
            target, request_id=document.odoo_sign_request_id, field_name=field_name,
        )
        saved = storage.archive_signed_contract_pdf(
            employee_id=employee_id, request_id=document.odoo_sign_request_id,
            payload=pdf,
        )
        document.odoo_sign_signed_storage_key = saved["key"]
        document.odoo_sign_signed_sha256 = saved["sha256"]
        document.odoo_sign_signed_attachment_id = attachment_id
        document.odoo_sign_signed_at = datetime.now(timezone.utc)
        db.commit()
    except (ArchiveNotReady, ArchiveUnavailable, sign_requests.SignTrackingConflict,
            sign_requests.SignTrackingUnavailable):
        db.rollback()
        raise
    except (staging.OdooNotConfigured, OdooClientError) as exc:
        db.rollback()
        raise ArchiveUnavailable("No fue posible consultar el PDF firmado en Odoo staging.") from exc
    except Exception as exc:
        db.rollback()
        raise ArchiveUnavailable("No se pudo almacenar la copia firmada en el expediente.") from exc
    return status(db, employee_id)


def download(db: Session, employee_id: str) -> dict:
    document = signing._contract(db, employee_id)
    if not document or not document.odoo_sign_signed_storage_key:
        raise ArchiveNotReady("El PDF firmado todavía no está archivado.")
    return {
        "filename": "ADN360_contrato_firmado.pdf",
        "url": storage.create_document_download_url(
            document.odoo_sign_signed_storage_key,
            filename="ADN360_contrato_firmado.pdf",
        ),
        "expires_in": storage.PRESIGNED_DOWNLOAD_EXPIRY_SECONDS,
    }
