"""S3 adapter for private employee documents."""

from __future__ import annotations

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
