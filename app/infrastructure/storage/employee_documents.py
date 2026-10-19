"""S3 adapter for private employee documents."""

from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import PurePosixPath

from app.config import get_aws_region, get_training_content_bucket
from app.infrastructure.bedrock.session import get_cached_session

PRESIGNED_UPLOAD_EXPIRY_SECONDS = 3600
PRESIGNED_DOWNLOAD_EXPIRY_SECONDS = 900
MAX_EMPLOYEE_DOCUMENT_BYTES = 15 * 1024 * 1024

CURRENT_DOCUMENT_PREFIX = "training/employee-documents"
LEGACY_DOCUMENT_PREFIX = "employees/documents"

ALLOWED_DOCUMENT_TYPES = {
    "application/pdf": {".pdf"},
    "image/jpeg": {".jpg", ".jpeg"},
    "image/png": {".png"},
    "application/msword": {".doc"},
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {
        ".docx"
    },
}


def _s3_client():
    return get_cached_session().client("s3", region_name=get_aws_region())


def _safe_filename(filename: str) -> str:
    basename = filename.replace("\\", "/").rsplit("/", 1)[-1]
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", basename).strip("._")
    return safe or "documento"


def _validate_upload(*, filename: str, content_type: str, size_bytes: int) -> str:
    normalized_type = str(content_type or "").split(";", 1)[0].strip().casefold()
    allowed_extensions = ALLOWED_DOCUMENT_TYPES.get(normalized_type)
    if not allowed_extensions:
        raise ValueError("Formato no soportado. Usa PDF, JPG, PNG, DOC o DOCX.")
    if size_bytes <= 0 or size_bytes > MAX_EMPLOYEE_DOCUMENT_BYTES:
        raise ValueError("El documento debe pesar máximo 15 MB.")

    suffix = PurePosixPath(filename.replace("\\", "/")).suffix.casefold()
    if suffix not in allowed_extensions:
        raise ValueError("La extensión del archivo no coincide con su tipo.")
    return normalized_type


def _employee_prefixes(employee_id: str) -> tuple[str, str]:
    return (
        f"{CURRENT_DOCUMENT_PREFIX}/{employee_id}/",
        f"{LEGACY_DOCUMENT_PREFIX}/{employee_id}/",
    )


def _is_document_key(key: str) -> bool:
    return str(key or "").startswith(
        (f"{CURRENT_DOCUMENT_PREFIX}/", f"{LEGACY_DOCUMENT_PREFIX}/")
    )


def create_document_upload(
    *,
    employee_id: str,
    filename: str,
    content_type: str,
    size_bytes: int,
) -> dict:
    normalized_type = _validate_upload(
        filename=filename,
        content_type=content_type,
        size_bytes=size_bytes,
    )
    safe_name = _safe_filename(filename)
    key = (
        f"{CURRENT_DOCUMENT_PREFIX}/{employee_id}/"
        f"{uuid.uuid4().hex}-{safe_name}"
    )
    upload = _s3_client().generate_presigned_post(
        Bucket=get_training_content_bucket(),
        Key=key,
        Fields={"Content-Type": normalized_type},
        Conditions=[
            {"key": key},
            {"Content-Type": normalized_type},
            ["content-length-range", size_bytes, size_bytes],
        ],
        ExpiresIn=PRESIGNED_UPLOAD_EXPIRY_SECONDS,
    )
    return {
        "key": key,
        "upload": upload,
        "expires_in": PRESIGNED_UPLOAD_EXPIRY_SECONDS,
        "max_size_bytes": MAX_EMPLOYEE_DOCUMENT_BYTES,
    }


def verify_document_object(
    *,
    employee_id: str,
    key: str,
    expected_content_type: str,
    expected_size_bytes: int,
) -> dict:
    if not str(key or "").startswith(_employee_prefixes(employee_id)):
        raise ValueError("El archivo no pertenece al empleado autenticado.")

    normalized_type = str(expected_content_type or "").split(";", 1)[0].strip().casefold()
    if normalized_type not in ALLOWED_DOCUMENT_TYPES:
        raise ValueError("Formato de documento no soportado.")
    if expected_size_bytes <= 0 or expected_size_bytes > MAX_EMPLOYEE_DOCUMENT_BYTES:
        raise ValueError("Tamaño de documento inválido.")

    response = _s3_client().head_object(
        Bucket=get_training_content_bucket(),
        Key=key,
    )
    actual_size = int(response.get("ContentLength") or 0)
    actual_type = str(response.get("ContentType") or "").split(";", 1)[0].strip().casefold()
    if actual_size != expected_size_bytes:
        raise ValueError("El tamaño cargado no coincide con el manifiesto.")
    if actual_type != normalized_type:
        raise ValueError("El tipo cargado no coincide con el manifiesto.")
    return {"key": key, "content_type": actual_type, "size_bytes": actual_size}


def create_document_download_url(key: str, *, filename: str) -> str:
    if not _is_document_key(key):
        raise ValueError("Clave de documento inválida.")
    safe_name = _safe_filename(filename)
    return _s3_client().generate_presigned_url(
        "get_object",
        Params={
            "Bucket": get_training_content_bucket(),
            "Key": key,
            "ResponseContentDisposition": f'attachment; filename="{safe_name}"',
        },
        ExpiresIn=PRESIGNED_DOWNLOAD_EXPIRY_SECONDS,
    )


def delete_document_object(key: str) -> None:
    if not _is_document_key(key):
        raise ValueError("Clave de documento inválida.")
    _s3_client().delete_object(Bucket=get_training_content_bucket(), Key=key)


def read_employee_pdf_for_signing(*, employee_id: str, key: str, expected_bytes: int) -> bytes:
    """Read only a validated employee-owned PDF from the private bucket."""
    if not str(key or "").startswith(_employee_prefixes(employee_id)):
        raise ValueError("El documento no corresponde al empleado.")
    if expected_bytes <= 0 or expected_bytes > MAX_EMPLOYEE_DOCUMENT_BYTES:
        raise ValueError("Tamaño del contrato no permitido.")
    response = _s3_client().get_object(
        Bucket=get_training_content_bucket(), Key=key
    )
    try:
        size = int(response.get("ContentLength") or 0)
        if size != expected_bytes:
            raise ValueError("El contrato almacenado cambió de tamaño.")
        body = response["Body"].read(MAX_EMPLOYEE_DOCUMENT_BYTES + 1)
    finally:
        response["Body"].close()
    if len(body) != expected_bytes or not body.startswith(b"%PDF-"):
        raise ValueError("Solo pueden prepararse contratos PDF válidos.")
    return body


def _archive_pdf_artifact(
    *, employee_id: str, request_id: int, payload: bytes, certificate: bool,
) -> dict:
    """Write a private, content-addressed PDF without altering the original."""
    if not isinstance(request_id, int) or request_id <= 0 or type(request_id) is bool:
        raise ValueError("Solicitud de firma inválida.")
    if not isinstance(payload, bytes) or not 100 <= len(payload) <= MAX_EMPLOYEE_DOCUMENT_BYTES:
        raise ValueError("Tamaño del PDF firmado fuera de los límites permitidos.")
    if not payload.startswith(b"%PDF-") or b"%%EOF" not in payload[-2048:]:
        raise ValueError("El archivo recuperado no parece un PDF completo.")
    digest = hashlib.sha256(payload).hexdigest()
    folder = "certificate/" if certificate else ""
    key = (
        f"{CURRENT_DOCUMENT_PREFIX}/{employee_id}/signed/"
        f"{request_id}/{folder}{digest}.pdf"
    )
    if not key.startswith(_employee_prefixes(employee_id)):
        raise ValueError("Destino de contrato firmado inválido.")
    _s3_client().put_object(
        Bucket=get_training_content_bucket(),
        Key=key,
        Body=payload,
        ContentType="application/pdf",
        ServerSideEncryption="AES256",
        Metadata={
            "sha256": digest,
            "odoo-sign-request-id": str(request_id),
            "odoo-sign-artifact": "certificate" if certificate else "signed-contract",
        },
    )
    return {"key": key, "sha256": digest, "size_bytes": len(payload)}


def archive_signed_contract_pdf(
    *, employee_id: str, request_id: int, payload: bytes,
) -> dict:
    return _archive_pdf_artifact(
        employee_id=employee_id, request_id=request_id, payload=payload,
        certificate=False,
    )


def archive_completion_certificate_pdf(
    *, employee_id: str, request_id: int, payload: bytes,
) -> dict:
    return _archive_pdf_artifact(
        employee_id=employee_id, request_id=request_id, payload=payload,
        certificate=True,
    )
