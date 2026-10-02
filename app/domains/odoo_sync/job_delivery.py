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
        "name": title,
        "description": job.get("description"),
        "active": True,
        "no_of_recruitment": 1,
        publication_field: published,
    }
    values = {
        field: value
        for field, value in desired.items()
        if field in writable and value is not None
    }
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
    transport = client or integration.build_odoo_client()

    sync.attempt_count = int(sync.attempt_count or 0) + 1
    sync.status = "PENDING"
    sync.last_error = None
    db.commit()
    db.refresh(sync)

    try:
        payload = dict(sync.payload or {})
        job_payload = dict(payload.get("job") or {})
        title = str(job_payload.get("title") or "").strip()
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
