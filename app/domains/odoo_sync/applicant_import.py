"""Incremental Odoo Recruitment -> Talent candidate ingestion.

Odoo remains the public application entry point. This module discovers applicants
per mapped vacancy, creates/reuses Talent candidates, copies one supported resume
into the existing ingestion staging area, and hands the document to the shared
candidate-ingestion worker.

Each mapped Odoo vacancy owns an independent write_date/id cursor. That prevents a
newly mapped vacancy from missing older applicants while keeping every subsequent
sync incremental and idempotent.
"""

from __future__ import annotations

import base64
import binascii
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_odoo_settings
from app.domains.candidate_ingestion import repository as ingestion_repository
from app.domains.candidates import identity as candidate_identity
from app.domains.candidates import repository as candidates_repository
from app.domains.odoo_sync import integration, service as odoo_sync_service
from app.infrastructure.imports.documents import MAX_DOCUMENT_BYTES
from app.infrastructure.imports import queue
from app.infrastructure.ingestion.storage import EmailIngestionStorage
from app.integrations.odoo.client import OdooClientError
from app.models import Job, OdooJobSync


SOURCE = "ATS"
PROVIDER = "ODOO"
DEFAULT_PAGE_SIZE = 100
_SUPPORTED_TYPES = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}


class OdooApplicantImportError(RuntimeError):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _text(value: Any) -> str | None:
    if value is None or value is False:
        return None
    normalized = " ".join(str(value).split()).strip()
    return normalized or None


def _email(value: Any) -> str | None:
    normalized = str(value or "").strip().casefold()
    if normalized.count("@") != 1:
        return None
    local, domain = normalized.split("@", 1)
    if not local or not domain or "." not in domain:
        return None
    return normalized


def _many2one_id(value: Any) -> int | None:
    if isinstance(value, (list, tuple)) and value:
        value = value[0]
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _many2one_name(value: Any) -> str | None:
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return _text(value[1])
    return None


def _candidate_name(row: dict) -> str:
    return (
        _text(row.get("partner_name"))
        or _text(row.get("name"))
        or f"Candidato Odoo {row.get('id')}"
    )


def _candidate_phone(row: dict) -> str | None:
    return _text(row.get("partner_phone")) or _text(row.get("mobile_phone"))


def _candidate_metadata(row: dict) -> dict:
    contact: dict[str, Any] = {}
    phone = _candidate_phone(row)
    if phone:
        contact["phone"] = phone
    linkedin = _text(row.get("linkedin_profile"))
    if linkedin:
        contact["linkedin"] = linkedin
    return {
        "source": "ODOO",
        "odoo_applicant_id": str(row.get("id")),
        "odoo_stage": _many2one_name(row.get("stage_id")),
        "odoo_created_at": _text(row.get("create_date")),
        "odoo_updated_at": _text(row.get("write_date")),
        "contact": contact,
    }


def _merge_candidate_metadata(candidate, row: dict) -> None:
    metadata = dict(candidate.metadata_ or {})
    incoming = _candidate_metadata(row)
    contact = dict(metadata.get("contact") or {})
    contact.update(incoming.pop("contact"))
    metadata.update(incoming)
    if contact:
        metadata["contact"] = contact
    candidate.metadata_ = metadata


def _candidate_identity_probe(row: dict):
    return SimpleNamespace(
        sha256="",
        email=_email(row.get("email_from")),
        phone=_candidate_phone(row),
        display_name=_candidate_name(row),
        filename=f"odoo-applicant-{row.get('id')}",
    )


def _applicant_fields(client) -> list[str]:
    fields = client.fields_get(
        "hr.applicant",
        attributes=("string", "type", "required", "readonly", "relation"),
    )
    preferred = (
        "id",
        "name",
        "partner_name",
        "email_from",
        "partner_phone",
        "mobile_phone",
        "linkedin_profile",
        "job_id",
        "stage_id",
        "message_main_attachment_id",
        "create_date",
        "write_date",
        "active",
    )
    return [name for name in preferred if name == "id" or name in fields]


def _attachment_fields(client) -> set[str]:
    fields = client.fields_get(
        "ir.attachment",
        attributes=("string", "type", "required", "readonly", "relation"),
    )
    return set(fields)


def _source_account(*, database: str, odoo_job_id: int) -> str:
    db_name = str(database or "odoo").strip() or "odoo"
    return f"{db_name}:hr.applicant:job:{odoo_job_id}"


def _encode_cursor(row: dict) -> str:
    write_date = _text(row.get("write_date"))
    if not write_date:
        raise OdooApplicantImportError("Odoo applicant write_date is required for incremental sync.")
    return json.dumps(
        {"write_date": write_date, "id": int(row["id"])},
        separators=(",", ":"),
        sort_keys=True,
    )


def _decode_cursor(value: str | None) -> tuple[str, int] | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        payload = json.loads(raw)
        write_date = str(payload["write_date"]).strip()
        row_id = int(payload["id"])
    except Exception as exc:
        raise OdooApplicantImportError("Stored Odoo applicant cursor is invalid.") from exc
    if not write_date or row_id <= 0:
        raise OdooApplicantImportError("Stored Odoo applicant cursor is invalid.")
    return write_date, row_id


def _cursor_domain(*, odoo_job_id: int, cursor_value: str | None) -> list:
    domain: list[Any] = [["job_id", "=", int(odoo_job_id)]]
    decoded = _decode_cursor(cursor_value)
    if decoded is None:
        return domain
    write_date, row_id = decoded
    domain.extend(
        [
            "|",
            ["write_date", ">", write_date],
            "&",
            ["write_date", "=", write_date],
            ["id", ">", row_id],
        ]
    )
    return domain


def _mapped_jobs(db: Session) -> list[tuple[OdooJobSync, Job]]:
    return (
        db.query(OdooJobSync, Job)
        .join(Job, Job.id == OdooJobSync.job_id)
        .filter(OdooJobSync.odoo_record_id.isnot(None))
        .order_by(Job.created_at.asc(), Job.id.asc())
        .all()
    )


def _normalize_filename(name: str | None, mimetype: str | None) -> tuple[str, str] | None:
    filename = _text(name) or "CV"
    normalized_type = str(mimetype or "").strip().casefold()
    extension = _SUPPORTED_TYPES.get(normalized_type)

    lower = filename.casefold()
    if lower.endswith(".pdf"):
        normalized_type = "application/pdf"
        extension = ".pdf"
    elif lower.endswith(".docx"):
        normalized_type = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        extension = ".docx"

    if extension is None:
        return None
    if not filename.casefold().endswith(extension):
        filename = f"{filename}{extension}"
    return filename, normalized_type


def _decode_attachment_data(value: Any) -> bytes:
    if value is None or value is False:
        return b""
    raw = getattr(value, "data", value)
    if isinstance(raw, bytes):
        # xmlrpc.client.Binary exposes decoded bytes through .data.
        return raw
    if isinstance(raw, str):
        try:
            return base64.b64decode(raw, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise OdooApplicantImportError("Odoo returned invalid attachment data.") from exc
    raise OdooApplicantImportError("Odoo returned an unsupported attachment payload.")


def _resume_attachment(client, *, row: dict, attachment_field_names: set[str]) -> dict | None:
    metadata_fields = [
        name
        for name in ("id", "name", "mimetype", "create_date")
        if name == "id" or name in attachment_field_names
    ]

    main_attachment_id = _many2one_id(row.get("message_main_attachment_id"))
    candidates: list[dict] = []
    if main_attachment_id is not None:
        candidates = client.search_read(
            "ir.attachment",
            [["id", "=", main_attachment_id]],
            fields=metadata_fields,
            limit=1,
        )

    if not candidates:
        candidates = client.search_read(
            "ir.attachment",
            [
                ["res_model", "=", "hr.applicant"],
                ["res_id", "=", int(row["id"])],
            ],
            fields=metadata_fields,
            limit=20,
            order="create_date desc, id desc",
        )

    for item in candidates:
        normalized = _normalize_filename(item.get("name"), item.get("mimetype"))
        if normalized is None:
            continue
        attachment_id = int(item["id"])
        data_rows = client.search_read(
            "ir.attachment",
            [["id", "=", attachment_id]],
            fields=[
                name
                for name in ("id", "name", "mimetype", "datas")
                if name == "id" or name in attachment_field_names
            ],
            limit=1,
        )
        if not data_rows:
            continue
        filename, content_type = normalized
        data = _decode_attachment_data(data_rows[0].get("datas"))
        if not data:
            continue
        if len(data) > MAX_DOCUMENT_BYTES:
            raise OdooApplicantImportError(
                f"Odoo resume attachment {attachment_id} exceeds the 15 MiB ingestion limit."
            )
        return {
            "id": attachment_id,
            "filename": filename,
            "content_type": content_type,
            "data": data,
        }
    return None


def _ensure_event(
    db: Session,
    *,
    owner_sub: str,
    source_account: str,
    row: dict,
    job: Job,
):
    external_id = str(row["id"])
    existing = ingestion_repository.get_event_by_external_id(
        db,
        owner_sub=owner_sub,
        source=SOURCE,
        provider=PROVIDER,
        source_account=source_account,
        external_id=external_id,
    )
    if existing is not None:
        return existing, False

    event = ingestion_repository.create_event(
        db,
        owner_sub=owner_sub,
        source=SOURCE,
        provider=PROVIDER,
        source_account=source_account,
        external_id=external_id,
        status="RECEIVED",
        raw_metadata={
            "odoo_applicant_id": external_id,
            "odoo_job_id": _many2one_id(row.get("job_id")),
            "candidate_name": _candidate_name(row),
            "candidate_email": _email(row.get("email_from")),
            "candidate_phone": _candidate_phone(row),
            "job_title": job.title,
            "odoo_stage": _many2one_name(row.get("stage_id")),
            "odoo_write_date": _text(row.get("write_date")),
        },
    )
    event.job_id = job.id
    db.commit()
    db.refresh(event)
    return event, True


def _resolve_candidate_and_application(
    db: Session,
    *,
    event,
    row: dict,
    job: Job,
    odoo_job_id: int,
):
    if event.candidate_id:
        candidate = candidates_repository.get_candidate(db, event.candidate_id)
        if candidate is None:
            raise OdooApplicantImportError("Previously imported Odoo candidate is missing.")
    else:
        candidate, _outcome = candidate_identity.resolve_or_create_candidate(
            db,
            owner_sub=event.owner_sub,
            parsed_document=_candidate_identity_probe(row),
        )
        _merge_candidate_metadata(candidate, row)
        event.candidate_id = candidate.id
        db.commit()

    application = candidates_repository.ensure_candidate_assigned_to_job(
        db,
        job_id=job.id,
        candidate_id=candidate.id,
    )
    odoo_sync_service.bind_imported_applicant(
        db,
        candidate=candidate,
        job=job,
        application=application,
        odoo_job_id=odoo_job_id,
        odoo_applicant_id=int(row["id"]),
    )
    db.commit()
    return candidate


def _attach_resume(
    db: Session,
    *,
    event,
    candidate,
    row: dict,
    attachment: dict | None,
    storage,
) -> bool:
    existing_documents = ingestion_repository.list_documents(db, event_id=event.id)
    if existing_documents:
        return True

    if attachment is None:
        event.status = "NEEDS_REVIEW"
        event.last_error_code = "RESUME_ATTACHMENT_MISSING"
        event.last_error_message = "Odoo applicant has no supported PDF or DOCX resume attachment."
        db.commit()
        return False

    candidates_repository.update_candidate_document_metadata(
        db,
        candidate,
        filename=attachment["filename"],
        email=_email(row.get("email_from")),
    )
    source_key = storage.store_source_document(
        event_id=event.id,
        attachment_id=str(attachment["id"]),
        filename=attachment["filename"],
        data=attachment["data"],
        content_type=attachment["content_type"],
    )
    ingestion_repository.create_document(
        db,
        ingestion_event_id=event.id,
        filename=attachment["filename"],
        content_type=attachment["content_type"],
        size_bytes=len(attachment["data"]),
        source_s3_key=source_key,
        document_sha256=None,
        status="STORED",
    )
    event.status = "STORED"
    event.last_error_code = None
    event.last_error_message = None
    db.commit()

    try:
        queue.send_candidate_ingestion(event.id)
    except Exception:
        # The shared worker's durable repair loop dispatches STORED events that
        # could not be queued during this request.
        db.rollback()
    else:
        event.queue_dispatched_at = _utcnow()
        db.commit()
    return True


def _process_applicant(
    db: Session,
    *,
    client,
    row: dict,
    job: Job,
    odoo_job_id: int,
    source_account: str,
    attachment_field_names: set[str],
    storage,
) -> tuple[bool, bool, bool]:
    owner_sub = str(job.owner_sub or "").strip()
    if not owner_sub:
        raise OdooApplicantImportError(
            f"Talent job {job.id} has no owner_sub and cannot ingest candidates safely."
        )

    event, created = _ensure_event(
        db,
        owner_sub=owner_sub,
        source_account=source_account,
        row=row,
        job=job,
    )
    try:
        candidate = _resolve_candidate_and_application(
            db,
            event=event,
            row=row,
            job=job,
            odoo_job_id=odoo_job_id,
        )
    except candidate_identity.CandidateIdentityConflict:
        event.status = "NEEDS_REVIEW"
        event.last_error_code = "IDENTITY_CONFLICT"
        event.last_error_message = (
            "Odoo applicant contact data matches different existing Talent candidates."
        )
        db.commit()
        return created, False, True

    attachment = _resume_attachment(
        client,
        row=row,
        attachment_field_names=attachment_field_names,
    )
    has_resume = _attach_resume(
        db,
        event=event,
        candidate=candidate,
        row=row,
        attachment=attachment,
        storage=storage,
    )
    return created, has_resume, event.status == "NEEDS_REVIEW"


def _sync_job(
    db: Session,
    *,
    client,
    sync: OdooJobSync,
    job: Job,
    database: str,
    applicant_fields: list[str],
    attachment_field_names: set[str],
    storage,
    page_size: int,
) -> dict:
    odoo_job_id = int(str(sync.odoo_record_id))
    source_account = _source_account(database=database, odoo_job_id=odoo_job_id)
    cursor = ingestion_repository.get_cursor(
        db,
        owner_sub=job.owner_sub,
        source=SOURCE,
        provider=PROVIDER,
        source_account=source_account,
    )

    discovered = created = existing = with_resume = without_resume = needs_review = 0
    cursor_value = cursor.cursor_value if cursor is not None else None

    while True:
        rows = client.search_read(
            "hr.applicant",
            _cursor_domain(
                odoo_job_id=odoo_job_id,
                cursor_value=cursor_value,
            ),
            fields=applicant_fields,
            limit=page_size,
            order="write_date asc, id asc",
        )
        if not rows:
            break

        for row in rows:
            discovered += 1
            was_created, has_resume, row_needs_review = _process_applicant(
                db,
                client=client,
                row=row,
                job=job,
                odoo_job_id=odoo_job_id,
                source_account=source_account,
                attachment_field_names=attachment_field_names,
                storage=storage,
            )
            if was_created:
                created += 1
            else:
                existing += 1
            if has_resume:
                with_resume += 1
            else:
                without_resume += 1
            if row_needs_review:
                needs_review += 1

        cursor_value = _encode_cursor(rows[-1])
        ingestion_repository.upsert_cursor(
            db,
            owner_sub=job.owner_sub,
            source=SOURCE,
            provider=PROVIDER,
            source_account=source_account,
            cursor_value=cursor_value,
        )
        db.commit()

        if len(rows) < page_size:
            break

    return {
        "job_id": job.id,
        "odoo_job_id": odoo_job_id,
        "title": job.title,
        "discovered": discovered,
        "created": created,
        "existing": existing,
        "with_resume": with_resume,
        "without_resume": without_resume,
        "needs_review": needs_review,
        "cursor": cursor_value,
    }


def sync_applicants_from_odoo(
    db: Session,
    *,
    client=None,
    storage=None,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> dict:
    """Incrementally import applicants and resumes for every mapped Talent vacancy."""

    transport = client or integration.build_odoo_client()
    source_storage = storage or EmailIngestionStorage()
    bounded_page_size = max(1, min(int(page_size), 500))
    database = get_odoo_settings().database or "odoo"

    try:
        applicant_fields = _applicant_fields(transport)
        if "write_date" not in applicant_fields or "job_id" not in applicant_fields:
            raise OdooApplicantImportError(
                "Odoo hr.applicant must expose job_id and write_date for safe incremental sync."
            )
        attachment_field_names = _attachment_fields(transport)

        jobs = _mapped_jobs(db)
        job_results = []
        for sync, job in jobs:
            stored_id = str(sync.odoo_record_id or "").strip()
            if not stored_id.isdigit():
                continue
            job_results.append(
                _sync_job(
                    db,
                    client=transport,
                    sync=sync,
                    job=job,
                    database=database,
                    applicant_fields=applicant_fields,
                    attachment_field_names=attachment_field_names,
                    storage=source_storage,
                    page_size=bounded_page_size,
                )
            )
    except OdooApplicantImportError:
        db.rollback()
        raise
    except OdooClientError as exc:
        db.rollback()
        raise OdooApplicantImportError(str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise OdooApplicantImportError("ODOO_APPLICANT_IMPORT_FAILED") from exc

    totals = {
        key: sum(int(item[key]) for item in job_results)
        for key in (
            "discovered",
            "created",
            "existing",
            "with_resume",
            "without_resume",
            "needs_review",
        )
    }
    return {
        "source": "ODOO",
        "model": "hr.applicant",
        "jobs_scanned": len(job_results),
        **totals,
        "jobs": job_results,
    }
