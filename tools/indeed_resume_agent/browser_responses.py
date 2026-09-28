from __future__ import annotations

import re
from email.header import decode_header, make_header
from urllib.parse import unquote, urlsplit

from .documents import (
    DOCX_CONTENT_TYPE,
    PDF_CONTENT_TYPE,
    InvalidResumeDocument,
    normalize_resume_filename,
    validate_resume_document,
)


_GENERIC_BINARY_CONTENT_TYPES = {
    "",
    "application/octet-stream",
    "binary/octet-stream",
}
_RESUME_DOWNLOAD_PATH = "/api/catws/resume/v2/download"
_FILENAME_STAR = re.compile(r"filename\*=UTF-8''([^;]+)", re.IGNORECASE)
_FILENAME_BASIC = re.compile(r'filename="?([^";]+)"?', re.IGNORECASE)
_MAX_RESUME_BYTES = 15 * 1024 * 1024


def response_filename_raw(response) -> str:
    headers = getattr(response, "headers", {}) or {}
    disposition = str(
        headers.get("content-disposition")
        or headers.get("Content-Disposition")
        or ""
    )
    candidate = ""
    match = _FILENAME_STAR.search(disposition)
    if match:
        candidate = unquote(match.group(1))
    else:
        match = _FILENAME_BASIC.search(disposition)
        if match:
            candidate = match.group(1).strip()
            try:
                candidate = str(make_header(decode_header(candidate)))
            except Exception:
                pass
    return candidate or "indeed-resume"


def response_filename(response, *, content_type: str = PDF_CONTENT_TYPE) -> str:
    return normalize_resume_filename(
        response_filename_raw(response),
        content_type=content_type,
    )


def response_document(response, *, probe_body: bool = True):
    if response is None or int(getattr(response, "status", 0) or 0) != 200:
        return None

    headers = getattr(response, "headers", {}) or {}
    content_type = str(
        headers.get("content-type") or headers.get("Content-Type") or ""
    ).split(";", 1)[0].strip().casefold()
    content_disposition = str(
        headers.get("content-disposition")
        or headers.get("Content-Disposition")
        or ""
    )
    response_url = str(getattr(response, "url", "") or "")
    disposition_lower = content_disposition.casefold()

    plausible_document = (
        content_type in {PDF_CONTENT_TYPE, DOCX_CONTENT_TYPE}
        or content_type in _GENERIC_BINARY_CONTENT_TYPES
        or "attachment" in disposition_lower
        or response_url.casefold().endswith((".pdf", ".docx"))
    )
    if not plausible_document and not probe_body:
        return None

    body = bytes(response.body() or b"")
    filename = response_filename_raw(response)
    try:
        canonical_type = validate_resume_document(
            body,
            filename=filename,
            content_type=content_type,
            max_bytes=_MAX_RESUME_BYTES,
        )
    except InvalidResumeDocument:
        # A declared supported resume must fail explicitly rather than being
        # mistaken for an ordinary HTML response.
        if (
            content_type in {PDF_CONTENT_TYPE, DOCX_CONTENT_TYPE}
            or response_url.casefold().endswith((".pdf", ".docx"))
            or "attachment" in disposition_lower
        ):
            raise
        return None

    return (
        body,
        canonical_type,
        normalize_resume_filename(filename, content_type=canonical_type),
    )


def response_pdf(response, *, probe_body: bool = True) -> bytes | None:
    """Compatibility helper retained for the existing test surface."""
    document = response_document(response, probe_body=probe_body)
    if document is None:
        return None
    data, content_type, _filename = document
    if content_type != PDF_CONTENT_TYPE:
        return None
    return data


def is_resume_download_response(response) -> bool:
    try:
        parsed = urlsplit(str(getattr(response, "url", "") or ""))
    except Exception:
        return False
    host = str(parsed.hostname or "").casefold()
    return (
        host == "employers.indeed.com"
        and parsed.path == _RESUME_DOWNLOAD_PATH
        and int(getattr(response, "status", 0) or 0) == 200
    )
