"""Private storage for employee-requested documents."""

from __future__ import annotations

import os
import re
import uuid

from app.config import get_aws_region
from app.infrastructure.bedrock.session import get_cached_session


PREFIX = "employee-documents"


def _bucket() -> str:
    value = os.getenv("S3_BUCKET", "").strip()
    if not value:
        raise RuntimeError("S3_BUCKET is not configured")
    return value


def _client():
    return get_cached_session().client("s3", region_name=get_aws_region())


def safe_filename(value: str) -> str:
    base = str(value or "document").replace("\\", "/").rsplit("/", 1)[-1]
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", base).strip("-.")
    return normalized[:120] or "document"


def put_employee_document(
    *,
    employee_id: str,
    request_id: str,
    filename: str,
    content_type: str,
    payload: bytes,
) -> str:
    key = (
        f"{PREFIX}/{employee_id}/{request_id}/"
        f"{uuid.uuid4().hex}-{safe_filename(filename)}"
    )
    _client().put_object(
        Bucket=_bucket(),
        Key=key,
        Body=payload,
        ContentType=content_type,
        ServerSideEncryption="AES256",
    )
    return key


def get_employee_document(storage_key: str) -> tuple[bytes, str | None]:
    response = _client().get_object(Bucket=_bucket(), Key=storage_key)
    body = response["Body"].read()
    return body, response.get("ContentType")


def delete_employee_document(storage_key: str | None) -> None:
    if not storage_key:
        return
    _client().delete_object(Bucket=_bucket(), Key=storage_key)
