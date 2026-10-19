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
    signed = bool(document and document.odoo_sign_signed_storage_key)
    certificate = bool(document and document.odoo_sign_certificate_storage_key)
    return {
        "archived": signed and certificate,
        "certificate_archived": certificate,
        "archived_at": (
            document.odoo_sign_signed_at.isoformat()
            if signed and certificate and document.odoo_sign_signed_at else None
        ),
        "sha256": document.odoo_sign_signed_sha256 if signed else None,
        "certificate_sha256": document.odoo_sign_certificate_sha256 if certificate else None,
        "staging_only": True,
    }


def _validated_pdf(item: dict) -> bytes:
    if str(item.get("mimetype") or "").casefold() != "application/pdf":
        raise ArchiveNotReady("Uno de los adjuntos finales de Odoo no es PDF.")
    encoded = item.get("datas")
    if not isinstance(encoded, str) or len(encoded) > (
        ((storage.MAX_EMPLOYEE_DOCUMENT_BYTES + 2) // 3) * 4 + 8
    ):
        raise ArchiveNotReady("Un adjunto final no está disponible o excede 15 MB.")
    try:
        pdf = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ArchiveNotReady("Un adjunto de Odoo no contiene un PDF íntegro.") from exc
    if item.get("file_size") not in (None, False) and int(item["file_size"]) != len(pdf):
        raise ArchiveNotReady("El tamaño de un PDF final no coincide.")
    if not 100 <= len(pdf) <= storage.MAX_EMPLOYEE_DOCUMENT_BYTES:
        raise ArchiveNotReady("PDF final fuera del límite de 15 MB.")
    if not pdf.startswith(b"%PDF-") or b"%%EOF" not in pdf[-2048:]:
        raise ArchiveNotReady("Un adjunto de Odoo no es un PDF completo.")
    return pdf


def _signed_attachments(
    target, *, request_id: int, field_name: str, expected_filename: str,
) -> tuple[tuple[int, bytes], tuple[int, bytes]]:
    """Identify exactly one signed contract and one completion certificate.

    Never select by ordering, file size or first match. Confirm each artifact
    belongs to the exact request, with an allowed signed-attachment relation.
    """
    request_fields = target.fields_get("sign.request")
    remote_field = request_fields.get(field_name)
    if not isinstance(remote_field, dict) or remote_field.get("type") != "many2many" or (
        remote_field.get("relation") != "ir.attachment"
    ):
        raise ArchiveUnavailable("Odoo Sign no expone la relación validada de adjuntos finales.")
    rows = target.search_read(
        "sign.request", [("id", "=", request_id)], fields=["id", field_name], limit=1,
    )
    if len(rows) != 1 or rows[0].get("id") != request_id:
        raise ArchiveNotReady("La solicitud firmada no se encuentra disponible.")
    ids = rows[0].get(field_name)
    if (not isinstance(ids, list) or len(ids) != 2
            or any(type(value) is not int or value <= 0 for value in ids)
            or len(set(ids)) != 2):
        raise ArchiveNotReady(
            "Odoo debe devolver exactamente un contrato firmado y su certificado."
        )

    fields = target.fields_get("ir.attachment")
    mandatory = {"id", "datas", "mimetype", "name", "res_model", "res_id"}
    if not mandatory.issubset(fields):
        raise ArchiveUnavailable("Odoo no permite verificar los dos documentos finales.")
    selected = sorted(mandatory | ({"file_size"} if "file_size" in fields else set()))
    attachments = target.search_read(
        "ir.attachment", [("id", "in", ids)], fields=selected, limit=3,
    )
    if len(attachments) != 2 or {item.get("id") for item in attachments} != set(ids):
        raise ArchiveNotReady("Los adjuntos finales de esta solicitud no están completos.")

    signed = None
    certificate = None
    for item in attachments:
        if item.get("res_model") != "sign.request" or item.get("res_id") != request_id:
            raise ArchiveNotReady("Un adjunto final pertenece a otra solicitud.")
        name = str(item.get("name") or "")
        if name == expected_filename and name.casefold().endswith(".pdf"):
            if signed is not None:
                raise ArchiveNotReady("Hay contratos firmados duplicados.")
            signed = (item["id"], _validated_pdf(item))
        elif name.casefold().startswith("certificate of completion - ") and name.casefold().endswith(".pdf"):
            if certificate is not None:
                raise ArchiveNotReady("Hay certificados de finalización duplicados.")
            certificate = (item["id"], _validated_pdf(item))
        else:
            raise ArchiveNotReady("Odoo devolvió un adjunto final que no se pudo identificar.")
    if signed is None or certificate is None:
        raise ArchiveNotReady("Falta el contrato firmado o su certificado de finalización.")
    return signed, certificate


def archive(db: Session, employee_id: str, *, client=None) -> dict:
    if not archive_enabled():
        raise ArchiveUnavailable("La copia de contratos firmados desde staging está deshabilitada.")
    sign_requests._require_fixture(employee_id)
    field_name = signed_artifact_field()

    document = signing._contract(db, employee_id)
    if document is None or document.odoo_sign_request_id is None:
        raise ArchiveNotReady("Debes vincular primero la solicitud de firma del contrato de prueba.")
    if document.odoo_sign_signed_storage_key and document.odoo_sign_certificate_storage_key:
        return status(db, employee_id)

    try:
        target = client or staging.build_staging_client()
        refreshed = sign_requests.track(db, employee_id, client=target)
        if refreshed["status"] != "SIGNED":
            raise ArchiveNotReady("Ambos firmantes deben completar la firma antes de archivar.")
        document = signing._contract(db, employee_id, lock=True)
        if document.odoo_sign_signed_storage_key and document.odoo_sign_certificate_storage_key:
            return status(db, employee_id)
        signed, certificate = _signed_attachments(
            target, request_id=document.odoo_sign_request_id, field_name=field_name,
            expected_filename=document.original_filename,
        )
        saved = storage.archive_signed_contract_pdf(
            employee_id=employee_id, request_id=document.odoo_sign_request_id,
            payload=signed[1],
        )
        saved_certificate = storage.archive_completion_certificate_pdf(
            employee_id=employee_id, request_id=document.odoo_sign_request_id,
            payload=certificate[1],
        )
        document.odoo_sign_signed_storage_key = saved["key"]
        document.odoo_sign_signed_sha256 = saved["sha256"]
        document.odoo_sign_signed_attachment_id = signed[0]
        document.odoo_sign_certificate_storage_key = saved_certificate["key"]
        document.odoo_sign_certificate_sha256 = saved_certificate["sha256"]
        document.odoo_sign_certificate_attachment_id = certificate[0]
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

def download_certificate(db: Session, employee_id: str) -> dict:
    document = signing._contract(db, employee_id)
    if not document or not document.odoo_sign_certificate_storage_key:
        raise ArchiveNotReady("El certificado de finalización todavía no está archivado.")
    return {
        "filename": "ADN360_certificado_de_firma.pdf",
        "url": storage.create_document_download_url(
            document.odoo_sign_certificate_storage_key,
            filename="ADN360_certificado_de_firma.pdf",
        ),
        "expires_in": storage.PRESIGNED_DOWNLOAD_EXPIRY_SECONDS,
    }
