"""Delivery of hired employees from the durable outbox to Odoo."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.domains.odoo_sync import integration
from app.integrations.odoo.client import OdooClientError
from app.models import OdooEmployeeSync


ODOO_COMPANY_NAME = "ASIATI"


class OdooEmployeeSyncNotFound(LookupError):
    pass


class OdooEmployeeSyncConflict(RuntimeError):
    pass


class OdooEmployeeDeliveryError(RuntimeError):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def require_employee_sync(db: Session, employee_id: str) -> OdooEmployeeSync:
    sync = (
        db.query(OdooEmployeeSync)
        .filter(OdooEmployeeSync.employee_id == employee_id)
        .one_or_none()
    )
    if sync is None:
        raise OdooEmployeeSyncNotFound(employee_id)
    return sync


def _writable_employee_fields(client) -> dict[str, dict[str, Any]]:
    fields = client.fields_get(
        "hr.employee",
        attributes=("string", "type", "required", "readonly", "relation", "selection"),
    )
    return {
        name: dict(metadata or {})
        for name, metadata in fields.items()
        if not bool((metadata or {}).get("readonly"))
    }


def _exact_named_id(client, model: str, name: str | None) -> int | None:
    normalized = str(name or "").strip()
    if not normalized:
        return None
    try:
        rows = client.search_read(
            model,
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


def build_hr_employee_values(client, payload: dict) -> tuple[dict, dict]:
    """Map the versioned local employee contract onto fields available in Odoo."""

    employee = dict(payload.get("employee") or {})
    candidate = dict(payload.get("candidate") or {})
    job = dict(payload.get("job") or {})
    writable = _writable_employee_fields(client)

    name = str(employee.get("name") or candidate.get("name") or "").strip()
    email = str(employee.get("email") or candidate.get("email") or "").strip()
    job_title = str(employee.get("job_title") or job.get("title") or "").strip()
    department = str(employee.get("department") or "").strip()
    private_phone = str(candidate.get("phone") or "").strip()

    if not name:
        raise OdooEmployeeDeliveryError("Employee name is required for Odoo.")
    if not email:
        raise OdooEmployeeDeliveryError("Employee email is required for Odoo.")

    desired = {
        "name": name,
        "work_email": email,
        "job_title": job_title or None,
        "private_phone": private_phone or None,
    }
    values = {
        field: value
        for field, value in desired.items()
        if value is not None and field in writable
    }

    employee_type = writable.get("employee_type") or {}
    selection = employee_type.get("selection") or []
    selection_keys = {
        str(item[0])
        for item in selection
        if isinstance(item, (list, tuple)) and item
    }
    if "employee" in selection_keys:
        values["employee_type"] = "employee"

    resolved = {
        "company_id": None,
        "department_id": None,
        "job_id": None,
        "company_matched": False,
        "department_matched": False,
        "job_matched": False,
    }

    if "company_id" in writable:
        company_id = _exact_named_id(client, "res.company", ODOO_COMPANY_NAME)
        if company_id is not None:
            values["company_id"] = company_id
            resolved["company_id"] = company_id
            resolved["company_matched"] = True
        elif bool((writable.get("company_id") or {}).get("required")):
            raise OdooEmployeeDeliveryError(
                "Odoo company ASIATI could not be resolved unambiguously."
            )

    if department and "department_id" in writable:
        department_id = _exact_named_id(client, "hr.department", department)
        if department_id is not None:
            values["department_id"] = department_id
            resolved["department_id"] = department_id
            resolved["department_matched"] = True

    if job_title and "job_id" in writable:
        job_id = _exact_named_id(client, "hr.job", job_title)
        if job_id is not None:
            values["job_id"] = job_id
            resolved["job_id"] = job_id
            resolved["job_matched"] = True

    if "name" not in values:
        raise OdooEmployeeDeliveryError(
            "Odoo hr.employee does not expose a writable name field."
        )
    return values, resolved


def _find_existing_employee_id(
    client,
    *,
    sync: OdooEmployeeSync,
    work_email: str,
) -> int | None:
    stored_id = str(sync.odoo_record_id or "").strip()
    if stored_id.isdigit():
        rows = client.search_read(
            "hr.employee",
            [["id", "=", int(stored_id)]],
            fields=["id"],
            limit=1,
        )
        if rows:
            return int(rows[0]["id"])

    rows = client.search_read(
        "hr.employee",
        [["work_email", "=ilike", work_email]],
        fields=["id", "work_email"],
        limit=2,
    )
    if len(rows) > 1:
        raise OdooEmployeeSyncConflict(
            "Multiple Odoo employees use the same work email."
        )
    if not rows:
        return None
    return int(rows[0]["id"])


def sync_employee_now(
    db: Session,
    *,
    employee_id: str,
    client=None,
) -> dict:
    """Synchronize one durable employee outbox row immediately."""

    sync = require_employee_sync(db, employee_id)
    transport = client or integration.build_odoo_client()

    sync.attempt_count = int(sync.attempt_count or 0) + 1
    sync.status = "PENDING"
    sync.last_error = None
    db.commit()
    db.refresh(sync)

    try:
        payload = dict(sync.payload or {})
        values, resolved = build_hr_employee_values(transport, payload)
        employee_payload = dict(payload.get("employee") or {})
        candidate_payload = dict(payload.get("candidate") or {})
        work_email = str(
            employee_payload.get("email")
            or candidate_payload.get("email")
            or ""
        ).strip()
        existing_id = _find_existing_employee_id(
            transport,
            sync=sync,
            work_email=work_email,
        )
        if existing_id is None:
            odoo_id = transport.create("hr.employee", values)
            action = "CREATED"
        else:
            transport.write("hr.employee", [existing_id], values)
            odoo_id = existing_id
            action = "UPDATED"

        sync.odoo_record_id = str(odoo_id)
        sync.status = "SYNCED"
        sync.last_error = None
        sync.synced_at = _utcnow()
        db.commit()
        db.refresh(sync)
        return {
            "employee_id": sync.employee_id,
            "status": sync.status,
            "attempt_count": sync.attempt_count,
            "odoo_record_id": sync.odoo_record_id,
            "action": action,
            "fields_written": sorted(values),
            "relations": resolved,
            "synced_at": sync.synced_at.isoformat() if sync.synced_at else None,
        }
    except (OdooEmployeeDeliveryError, OdooEmployeeSyncConflict, OdooClientError) as exc:
        sync.status = "FAILED"
        sync.last_error = str(exc)
        sync.synced_at = None
        db.commit()
        raise OdooEmployeeDeliveryError(str(exc)) from exc
    except Exception as exc:
        sync.status = "FAILED"
        sync.last_error = "ODOO_EMPLOYEE_SYNC_FAILED"
        sync.synced_at = None
        db.commit()
        raise OdooEmployeeDeliveryError("ODOO_EMPLOYEE_SYNC_FAILED") from exc
