"""Resume document validation and filename normalization."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path


PDF_CONTENT_TYPE = "application/pdf"
DOCX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


class InvalidResumeDocument(ValueError):
    def __init__(self, code: str):
        self.code = str(code)
        super().__init__(self.code)


# Backwards-compatible name for callers/tests that imported the former PDF-only
# exception. The agent now accepts PDF and DOCX.
InvalidResumePdf = InvalidResumeDocument


def _is_docx(payload: bytes) -> bool:
    if not payload.startswith(b"PK"):
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
            names = set(archive.namelist())
    except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError):
        return False
    return "[Content_Types].xml" in names and "word/document.xml" in names


def validate_resume_document(
    data: bytes,
    *,
    filename: str | None = None,
    content_type: str | None = None,
    max_bytes: int,
) -> str:
    """Validate a supported resume and return its canonical MIME type."""
    payload = bytes(data or b"")
    if len(payload) > int(max_bytes):
        raise InvalidResumeDocument("RESUME_TOO_LARGE")

    declared = str(content_type or "").split(";", 1)[0].strip().casefold()
    suffix = Path(str(filename or "")).suffix.casefold()

    if payload.startswith(b"%PDF-"):
        return PDF_CONTENT_TYPE
    if _is_docx(payload):
        return DOCX_CONTENT_TYPE

    if declared == PDF_CONTENT_TYPE or suffix == ".pdf":
        raise InvalidResumeDocument("RESUME_NOT_PDF")
    if declared == DOCX_CONTENT_TYPE or suffix == ".docx":
        raise InvalidResumeDocument("RESUME_NOT_DOCX")
    raise InvalidResumeDocument("RESUME_UNSUPPORTED_FORMAT")


def validate_pdf(data: bytes, *, max_bytes: int) -> None:
    """Compatibility wrapper for legacy PDF-only callers."""
    detected = validate_resume_document(
        data,
        filename="resume.pdf",
        content_type=PDF_CONTENT_TYPE,
        max_bytes=max_bytes,
    )
    if detected != PDF_CONTENT_TYPE:
        raise InvalidResumeDocument("RESUME_NOT_PDF")


def normalize_resume_filename(
    filename: str | None,
    *,
    content_type: str,
) -> str:
    raw = str(filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    stem = Path(raw).stem.strip() if raw else "indeed-resume"
    safe = "".join(
        ch if ch.isalnum() or ch in " ._-" else "_"
        for ch in stem
    ).strip()
    extension = ".docx" if content_type == DOCX_CONTENT_TYPE else ".pdf"
    return f"{safe or 'indeed-resume'}{extension}"


def normalize_pdf_filename(filename: str | None) -> str:
    return normalize_resume_filename(filename, content_type=PDF_CONTENT_TYPE)
