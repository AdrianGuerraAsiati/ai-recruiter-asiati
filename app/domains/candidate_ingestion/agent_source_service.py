"""Provider-neutral machine-agent handoff for externally sourced candidates."""

from __future__ import annotations

import hashlib
import io
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePosixPath

from sqlalchemy.orm import Session

from app.domains.candidate_ingestion import repository
from app.infrastructure.imports import queue
from app.infrastructure.ingestion.storage import EmailIngestionStorage

MAX_DOCUMENT_BYTES = 15 * 1024 * 1024
PDF_CONTENT_TYPE = "application/pdf"
DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
SUPPORTED_PROVIDERS = frozenset({"COMPUTRABAJO"})


class CandidateSourceValidationError(ValueError):
    def __init__(self, status_code: int, code: str):
        self.status_code = int(status_code)
        self.code = str(code)
        super().__init__(self.code)


@dataclass(frozen=True)
class CandidateSourceIngestionResult:
    event_id: str
    provider: str
    status: str
    existing: bool
    queued: bool


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_pdf(data: bytes) -> bool:
    return bytes(data or b"").lstrip().startswith(b"%PDF-")


def _is_docx(data: bytes) -> bool:
    payload = bytes(data or b"")
    if not payload.startswith(b"PK"):
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = set(archive.namelist())
    except (OSError, zipfile.BadZipFile):
        return False
    return "[Content_Types].xml" in names and "word/document.xml" in names


def _validate_document(*, filename: str | None, content_type: str, data: bytes) -> str:
    payload = bytes(data or b"")
    if not payload:
        raise CandidateSourceValidationError(422, "CANDIDATE_SOURCE_DOCUMENT_EMPTY")
    if len(payload) > MAX_DOCUMENT_BYTES:
        raise CandidateSourceValidationError(413, "CANDIDATE_SOURCE_DOCUMENT_TOO_LARGE")

    suffix = PurePosixPath(str(filename or "")).suffix.casefold()
    declared = str(content_type or "").split(";", 1)[0].strip().casefold()

    if _is_pdf(payload):
        if suffix not in {"", ".pdf"}:
            raise CandidateSourceValidationError(422, "CANDIDATE_SOURCE_DOCUMENT_EXTENSION_INVALID")
        if declared not in {"", "application/octet-stream", PDF_CONTENT_TYPE}:
            raise CandidateSourceValidationError(422, "CANDIDATE_SOURCE_DOCUMENT_TYPE_INVALID")
        return PDF_CONTENT_TYPE

    if _is_docx(payload):
        if suffix not in {"", ".docx"}:
            raise CandidateSourceValidationError(422, "CANDIDATE_SOURCE_DOCUMENT_EXTENSION_INVALID")
        if declared not in {"", "application/octet-stream", DOCX_CONTENT_TYPE}:
            raise CandidateSourceValidationError(422, "CANDIDATE_SOURCE_DOCUMENT_TYPE_INVALID")
        return DOCX_CONTENT_TYPE

    raise CandidateSourceValidationError(422, "CANDIDATE_SOURCE_DOCUMENT_UNSUPPORTED")


def _safe_filename(filename: str | None, *, content_type: str) -> str:
    raw = str(filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    stem = PurePosixPath(raw).stem.strip() if raw else "candidate-resume"
    safe = "".join(ch if ch.isalnum() or ch in " ._-" else "_" for ch in stem).strip()
    extension = ".docx" if content_type == DOCX_CONTENT_TYPE else ".pdf"
    return f"{safe or 'candidate-resume'}{extension}"


def ingest_candidate_document(
    db: Session,
    *,
    owner_sub: str,
    provider: str,
    source_account: str,
    external_id: str,
    candidate_name: str,
    job_title: str,
    filename: str | None,
    content_type: str,
    data: bytes,
    external_job_id: str | None = None,
    location: str | None = None,
    applied_at: str | None = None,
    storage=None,
) -> CandidateSourceIngestionResult:
    """Persist one external candidate idempotently and hand it to the shared pipeline."""
    normalized_provider = str(provider or "").strip().upper()
    if normalized_provider not in SUPPORTED_PROVIDERS:
        raise CandidateSourceValidationError(422, "CANDIDATE_SOURCE_PROVIDER_UNSUPPORTED")

    normalized_account = str(source_account or "").strip()
    normalized_external_id = str(external_id or "").strip()
    normalized_name = " ".join(str(candidate_name or "").split()).strip()
    if not normalized_account or not normalized_external_id:
        raise CandidateSourceValidationError(422, "CANDIDATE_SOURCE_IDENTITY_MISSING")
    if not normalized_name:
        raise CandidateSourceValidationError(422, "CANDIDATE_SOURCE_CONTEXT_MISSING")

    payload = bytes(data or b"")
    canonical_type = _validate_document(
        filename=filename,
        content_type=content_type,
        data=payload,
    )
    digest = hashlib.sha256(payload).hexdigest()

    existing = repository.get_event_by_external_id(
        db,
        owner_sub=owner_sub,
        source="AGENT",
        provider=normalized_provider,
        source_account=normalized_account,
        external_id=normalized_external_id,
    )
    if existing is not None:
        documents = repository.list_documents(db, event_id=existing.id)
        if len(documents) == 1 and documents[0].document_sha256 == digest:
            queued = bool(existing.queue_dispatched_at)
            # An earlier SQS outage must not strand a stored candidate forever.
            if not queued:
                try:
                    queue.send_candidate_ingestion(existing.id)
                except Exception:
                    db.rollback()
                else:
                    existing.queue_dispatched_at = _now()
                    db.commit()
                    queued = True
            return CandidateSourceIngestionResult(
                event_id=str(existing.id),
                provider=normalized_provider,
                status=str(existing.status),
                existing=True,
                queued=queued,
            )
        raise CandidateSourceValidationError(409, "CANDIDATE_SOURCE_EVENT_CONFLICT")

    metadata = {
        "candidate_name": normalized_name,
        "source_provider": normalized_provider,
    }
    if location:
        metadata["location"] = " ".join(str(location).split()).strip()
    if applied_at:
        metadata["applied_at"] = str(applied_at).strip()

    event = repository.create_event(
        db,
        owner_sub=owner_sub,
        source="AGENT",
        provider=normalized_provider,
        source_account=normalized_account,
        external_id=normalized_external_id,
        status="RECEIVED",
        raw_metadata=metadata,
    )
    # Computrabajo is a candidate source only: NEVER resolve or assign a Talent job.
    # Provider-side offers are navigation paths, not jobs in the Talent domain.

    safe_filename = _safe_filename(filename, content_type=canonical_type)
    source_storage = storage or EmailIngestionStorage()
    source_key = source_storage.store_source_document(
        event_id=str(event.id),
        attachment_id=f"{normalized_provider.casefold()}-{normalized_external_id}",
        filename=safe_filename,
        data=payload,
        content_type=canonical_type,
    )
    repository.create_document(
        db,
        ingestion_event_id=event.id,
        filename=safe_filename,
        content_type=canonical_type,
        size_bytes=len(payload),
        source_s3_key=source_key,
        document_sha256=digest,
        status="STORED",
    )
    event.status = "STORED"
    event.last_error_code = None
    event.last_error_message = None
    event.queue_dispatched_at = None
    db.commit()
    db.refresh(event)

    queued = False
    try:
        queue.send_candidate_ingestion(event.id)
    except Exception:
        db.rollback()
    else:
        event.queue_dispatched_at = _now()
        db.commit()
        queued = True

    return CandidateSourceIngestionResult(
        event_id=str(event.id),
        provider=normalized_provider,
        status=str(event.status),
        existing=False,
        queued=queued,
    )
