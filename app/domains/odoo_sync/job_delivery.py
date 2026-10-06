"""Delivery of Talent vacancies from the durable outbox into Odoo."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.domains.odoo_sync import integration
from app.integrations.odoo.client import OdooClientError
from app.models import OdooJobSync


class OdooJobSyncNotFound(LookupError):
    pass


class OdooJobSyncConflict(RuntimeError):
    pass


class OdooJobDeliveryError(RuntimeError):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def require_job_sync(db: Session, job_id: str) -> OdooJobSync:
    sync = (
        db.query(OdooJobSync)
        .filter(OdooJobSync.job_id == job_id)
        .one_or_none()
    )
    if sync is None:
        raise OdooJobSyncNotFound(job_id)
    return sync


def _writable_job_fields(client) -> dict[str, dict[str, Any]]:
    fields = client.fields_get(
        "hr.job",
        attributes=("string", "type", "required", "readonly", "relation", "selection"),
    )
    return {
        name: dict(metadata or {})
        for name, metadata in fields.items()
        if not bool((metadata or {}).get("readonly"))
    }


def _publication_field(writable: dict[str, dict[str, Any]]) -> str:
    for field in ("website_published", "is_published"):
        if field in writable:
            return field
    raise OdooJobDeliveryError(
        "Odoo hr.job does not expose a writable website publication field."
    )


def _exact_address_id(
    client,
    *,
    city: str | None,
    country_code: str | None,
) -> int | None:
    normalized_city = str(city or "").strip()
    normalized_country = str(country_code or "").strip().upper()
    if not normalized_city:
        return None

    domain = [["city", "=ilike", normalized_city]]
    if normalized_country:
        domain.append(["country_id.code", "=", normalized_country])
    try:
        rows = client.search_read(
            "res.partner",
            domain,
            fields=["id", "city"],
            limit=20,
        )
    except OdooClientError:
        return None

    exact = [
        row
        for row in rows
        if str(row.get("city") or "").strip().casefold()
        == normalized_city.casefold()
    ]
    if len(exact) != 1:
        return None
    return int(exact[0]["id"])


def _company_id(client, company_name: str | None) -> int | None:
    normalized = str(company_name or "").strip()
    if not normalized:
        return None
    try:
        rows = client.search_read(
            "res.company",
            [["name", "=ilike", normalized]],
            fields=["id", "name"],
            limit=10,
        )
    except OdooClientError:
        return None

    exact = [
        row
        for row in rows
        if str(row.get("name") or "").strip().casefold() == normalized.casefold()
    ]
    if len(exact) != 1:
        return None
    return int(exact[0]["id"])


def _employment_type_id(client, value: str | None) -> int | None:
    normalized = str(value or "").strip().upper()
    if not normalized:
        return None

    aliases = {
        "FULL_TIME": ("Full-Time", "Full Time"),
        "PERMANENT": ("Permanent",),
        "TEMPORARY": ("Temporary",),
        "SEASONAL": ("Seasonal",),
        "INTERN": ("Intern",),
        "STUDENT": ("Student",),
        "APPRENTICESHIP": ("Apprenticeship",),
        "THESIS": ("Thesis",),
        "STATUTORY": ("Statutory",),
        "EMPLOYEE": ("Employee",),
    }
    candidates = aliases.get(
        normalized,
        (normalized.replace("_", " ").title(),),
    )

    for candidate in candidates:
        try:
            rows = client.search_read(
                "hr.contract.type",
                [["name", "=ilike", candidate]],
                fields=["id", "name"],
                limit=10,
            )
        except OdooClientError:
            return None
        exact = [
            row
            for row in rows
            if str(row.get("name") or "").strip().casefold()
            == candidate.casefold()
        ]
        if len(exact) == 1:
            return int(exact[0]["id"])
    return None


_TITLE_ACRONYMS = {
    "API", "APIS", "ASIATI", "AWS", "BI", "BPO", "CEO", "CFO", "COO", "CRM",
    "CTO", "ERP", "HR", "IA", "IT", "KAM", "LATAM", "QA", "SAP", "SQL", "TI",
    "UI", "UX",
}
_TITLE_LOWER_WORDS = {
    "a", "al", "con", "de", "del", "e", "el", "en", "la", "las", "los",
    "o", "para", "por", "sin", "u", "y",
}


def _display_job_title(value: str | None) -> str:
    """Return a human-friendly title without mutating Talent's stored title."""

    source = str(value or "").strip()
    if not source:
        return ""

    rendered: list[str] = []
    word_index = 0
    for token in source.split():
        separators = ("–", "—")
        if token in separators:
            rendered.append(token)
            continue

        pieces: list[str] = []
        current = ""
        for char in token:
            if char in "/-":
                if current:
                    pieces.append(current)
                    current = ""
                pieces.append(char)
            else:
                current += char
        if current:
            pieces.append(current)

        output: list[str] = []
        for piece in pieces:
            if piece in {"/", "-"}:
                output.append(piece)
                continue

            suffix = ""
            base = piece
            if len(piece) > 3 and piece[-3:].lower() in {"(a)", "(o)"}:
                base, suffix = piece[:-3], piece[-3:].lower()

            upper = base.upper()
            lower = base.lower()
            if upper in _TITLE_ACRONYMS:
                normalized = upper
            elif word_index > 0 and lower in _TITLE_LOWER_WORDS:
                normalized = lower
            else:
                normalized = lower[:1].upper() + lower[1:]

            output.append(normalized + suffix)
            word_index += 1

        rendered.append("".join(output))

    return " ".join(rendered)


def build_hr_job_values(client, payload: dict) -> tuple[dict, str]:
    """Map the stable Talent vacancy contract onto writable Odoo hr.job fields."""

    job = dict(payload.get("job") or {})
    writable = _writable_job_fields(client)

    title = str(job.get("title") or "").strip()
    if not title:
        raise OdooJobDeliveryError("Vacancy title is required for Odoo.")
    if "name" not in writable:
        raise OdooJobDeliveryError(
            "Odoo hr.job does not expose a writable name field."
        )

    status = str(job.get("status") or "ACTIVE").strip().upper()
    published = status == "ACTIVE"
    publication_field = _publication_field(writable)

    desired = {
        "name": _display_job_title(title),
        "description": job.get("description"),
        "active": published,
        "no_of_recruitment": 1,
        publication_field: published,
    }
    values = {
        field: value
        for field, value in desired.items()
        if field in writable and value is not None
    }

    if "company_id" in writable:
        company_id = _company_id(client, job.get("company_name"))
        if company_id is not None:
            values["company_id"] = company_id

    if "address_id" in writable and str(job.get("city") or "").strip():
        address_id = _exact_address_id(
            client,
            city=job.get("city"),
            country_code=job.get("country_code"),
        )
        # An unresolved Talent location is safer as remote/unspecified than
        # allowing Odoo to apply the last-used office as a misleading default.
        values["address_id"] = address_id or False

    if "contract_type_id" in writable:
        contract_type_id = _employment_type_id(
            client,
            job.get("employment_type"),
        )
        if contract_type_id is not None:
            values["contract_type_id"] = contract_type_id

    return values, publication_field


def _find_existing_job_id(
    client,
    *,
    sync: OdooJobSync,
    title: str,
) -> int | None:
    stored_id = str(sync.odoo_record_id or "").strip()
    if stored_id.isdigit():
        rows = client.search_read(
            "hr.job",
            [["id", "=", int(stored_id)]],
            fields=["id"],
            limit=1,
        )
        if rows:
            return int(rows[0]["id"])

    rows = client.search_read(
        "hr.job",
        [["name", "=ilike", title]],
        fields=["id", "name"],
        limit=10,
    )
    exact = [
        row
        for row in rows
        if str(row.get("name") or "").strip().casefold() == title.casefold()
    ]
    if len(exact) > 1:
        raise OdooJobSyncConflict(
            "Multiple Odoo vacancies use the same exact title."
        )
    if not exact:
        return None
    return int(exact[0]["id"])


def sync_job_now(
    db: Session,
    *,
    job_id: str,
    client=None,
) -> dict:
    """Synchronize one Talent vacancy with Odoo immediately and idempotently."""

    sync = require_job_sync(db, job_id)

    sync.attempt_count = int(sync.attempt_count or 0) + 1
    sync.status = "PENDING"
    sync.last_error = None
    db.commit()
    db.refresh(sync)

    try:
        payload = dict(sync.payload or {})
        job_payload = dict(payload.get("job") or {})
        title = str(job_payload.get("title") or "").strip()
        status = str(job_payload.get("status") or "ACTIVE").strip().upper()

        stored_odoo_id = str(sync.odoo_record_id or "").strip()
        if status != "ACTIVE":
            if not stored_odoo_id:
                sync.status = "SYNCED"
                sync.last_error = None
                sync.synced_at = _utcnow()
                db.commit()
                db.refresh(sync)
                return {
                    "job_id": sync.job_id,
                    "status": sync.status,
                    "attempt_count": sync.attempt_count,
                    "odoo_record_id": None,
                    "action": "SKIPPED",
                    "publication_field": None,
                    "published": False,
                    "fields_written": [],
                    "synced_at": sync.synced_at.isoformat() if sync.synced_at else None,
                }

            transport = client or integration.build_odoo_client()
            record_id = int(stored_odoo_id)
            existing = transport.search_read(
                "hr.job",
                [["id", "=", record_id]],
                fields=["id"],
                limit=1,
            )
            action = "ALREADY_ABSENT"
            if existing:
                if not transport.unlink("hr.job", [record_id]):
                    raise OdooJobDeliveryError(
                        "Odoo did not confirm vacancy deletion."
                    )
                action = "DELETED"

            sync.odoo_record_id = None
            sync.status = "SYNCED"
            sync.last_error = None
            sync.synced_at = _utcnow()
            db.commit()
            db.refresh(sync)
            return {
                "job_id": sync.job_id,
                "status": sync.status,
                "attempt_count": sync.attempt_count,
                "odoo_record_id": None,
                "action": action,
                "publication_field": None,
                "published": False,
                "fields_written": [],
                "synced_at": sync.synced_at.isoformat() if sync.synced_at else None,
            }

        transport = client or integration.build_odoo_client()
        values, publication_field = build_hr_job_values(transport, payload)
        existing_id = _find_existing_job_id(
            transport,
            sync=sync,
            title=title,
        )

        if existing_id is None:
            odoo_id = transport.create("hr.job", values)
            action = "CREATED"
        else:
            transport.write("hr.job", [existing_id], values)
            odoo_id = existing_id
            action = "UPDATED"

        sync.odoo_record_id = str(odoo_id)
        sync.status = "SYNCED"
        sync.last_error = None
        sync.synced_at = _utcnow()
        db.commit()
        db.refresh(sync)
        return {
            "job_id": sync.job_id,
            "status": sync.status,
            "attempt_count": sync.attempt_count,
            "odoo_record_id": sync.odoo_record_id,
            "action": action,
            "publication_field": publication_field,
            "published": bool(values.get(publication_field)),
            "fields_written": sorted(values),
            "synced_at": sync.synced_at.isoformat() if sync.synced_at else None,
        }
    except (OdooJobDeliveryError, OdooJobSyncConflict, OdooClientError) as exc:
        sync.status = "FAILED"
        sync.last_error = str(exc)
        sync.synced_at = None
        db.commit()
        raise OdooJobDeliveryError(str(exc)) from exc
    except Exception as exc:
        sync.status = "FAILED"
        sync.last_error = "ODOO_JOB_SYNC_FAILED"
        sync.synced_at = None
        db.commit()
        raise OdooJobDeliveryError("ODOO_JOB_SYNC_FAILED") from exc


def sync_all_jobs_now(db: Session, *, client=None) -> dict:
    """Backfill and deliver every unsynchronized Talent vacancy to Odoo."""

    from app.domains.odoo_sync import service as sync_service
    from app.models import Job

    jobs = db.query(Job).order_by(Job.created_at.asc(), Job.id.asc()).all()
    pending_job_ids: list[str] = []
    skipped = 0
    active_total = 0
    paused_total = 0

    for job in jobs:
        sync = sync_service.ensure_job_sync(db, job=job)
        db.commit()
        db.refresh(sync)

        status = str(getattr(job, "status", None) or "ACTIVE").strip().upper()
        if status == "ACTIVE":
            active_total += 1
            # Reconcile every active vacancy on each explicit/backfill sync.
            # A historic SYNCED marker only means the previous delivery attempt
            # finished; it does not prove that the remote hr.job still exists
            # or remains published in Odoo.
            pending_job_ids.append(job.id)
            continue

        paused_total += 1
        # Paused vacancies only need Odoo I/O when there is a known remote
        # record to delete, or when a previous attempt failed/pended.
        if str(sync.odoo_record_id or "").strip() or sync.status != "SYNCED":
            pending_job_ids.append(job.id)
        else:
            skipped += 1

    if not pending_job_ids:
        return {
            "total": len(jobs),
            "active_total": active_total,
            "paused_total": paused_total,
            "attempted": 0,
            "synced": 0,
            "failed": 0,
            "skipped": skipped,
        }

    transport = client
    synced = 0
    failed = 0
    for job_id in pending_job_ids:
        sync = require_job_sync(db, job_id)
        job_payload = dict((sync.payload or {}).get("job") or {})
        status = str(job_payload.get("status") or "ACTIVE").strip().upper()
        requires_transport = status == "ACTIVE" or bool(
            str(sync.odoo_record_id or "").strip()
        )
        if requires_transport and transport is None:
            transport = integration.build_odoo_client()
        try:
            result = sync_job_now(
                db,
                job_id=job_id,
                client=transport if requires_transport else None,
            )
            if result.get("action") == "SKIPPED":
                skipped += 1
            else:
                synced += 1
        except OdooJobDeliveryError:
            failed += 1

    return {
        "total": len(jobs),
        "active_total": active_total,
        "paused_total": paused_total,
        "attempted": len(pending_job_ids),
        "synced": synced,
        "failed": failed,
        "skipped": skipped,
    }
