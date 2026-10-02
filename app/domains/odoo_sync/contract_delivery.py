"""Delivery of employee contracts from the durable outbox to Odoo."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.domains.odoo_sync import integration
from app.integrations.odoo.client import OdooClientError
from app.models import OdooContractSync, OdooEmployeeSync


class OdooContractSyncNotFound(LookupError):
    pass


class OdooContractDependencyError(RuntimeError):
    pass


class OdooContractSyncConflict(RuntimeError):
    pass


class OdooContractDeliveryError(RuntimeError):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def require_contract_sync(db: Session, employee_id: str) -> OdooContractSync:
    sync = (
        db.query(OdooContractSync)
        .filter(OdooContractSync.employee_id == employee_id)
        .one_or_none()
    )
    if sync is None:
        raise OdooContractSyncNotFound(employee_id)
    return sync


def _writable_contract_fields(client) -> dict[str, dict[str, Any]]:
    fields = client.fields_get(
        "hr.contract",
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


def _employee_odoo_id(db: Session, employee_id: str) -> int:
    employee_sync = (
        db.query(OdooEmployeeSync)
        .filter(OdooEmployeeSync.employee_id == employee_id)
        .one_or_none()
    )
    stored_id = str(employee_sync.odoo_record_id or "").strip() if employee_sync else ""
    if not stored_id.isdigit():
        raise OdooContractDependencyError(
            "Employee must be synchronized to Odoo before its contract."
        )
    return int(stored_id)


def build_hr_contract_values(
    client,
    payload: dict,
    *,
    employee_odoo_id: int,
) -> tuple[dict, dict]:
    """Map the local contract payload onto writable fields in hr.contract."""

    contract = dict(payload.get("contract") or {})
    employee = dict(payload.get("employee") or {})
    writable = _writable_contract_fields(client)

    name = str(contract.get("name") or "").strip()
    start_date = str(contract.get("start_date") or "").strip()
    end_date = str(contract.get("end_date") or "").strip()
    contract_type = str(contract.get("contract_type") or "").strip()
    wage = contract.get("monthly_wage")

    if not name:
        name = f"Contrato - {str(employee.get('name') or '').strip()}".strip(" -")
    if not start_date:
        raise OdooContractDeliveryError("Contract start date is required for Odoo.")
    if wage in (None, ""):
        raise OdooContractDeliveryError("Contract monthly wage is required for Odoo.")

    required_local_fields = {"employee_id", "date_start"}
    missing = sorted(field for field in required_local_fields if field not in writable)
    if missing:
        raise OdooContractDeliveryError(
            "Odoo hr.contract does not expose required writable fields: "
            + ", ".join(missing)
        )

    desired = {
        "name": name,
        "employee_id": employee_odoo_id,
        "date_start": start_date,
        "date_end": end_date or None,
        "wage": float(wage),
    }
    values = {
        field: value
        for field, value in desired.items()
        if value is not None and field in writable
    }

    resolved = {
        "employee_id": employee_odoo_id,
        "contract_type_id": None,
        "contract_type_matched": False,
    }
    if contract_type and "contract_type_id" in writable:
        contract_type_id = _exact_named_id(client, "hr.contract.type", contract_type)
        if contract_type_id is not None:
            values["contract_type_id"] = contract_type_id
            resolved["contract_type_id"] = contract_type_id
            resolved["contract_type_matched"] = True

    return values, resolved


def _find_existing_contract_id(
    client,
    *,
    sync: OdooContractSync,
    employee_odoo_id: int,
    start_date: str,
) -> int | None:
    stored_id = str(sync.odoo_record_id or "").strip()
    if stored_id.isdigit():
        rows = client.search_read(
            "hr.contract",
            [["id", "=", int(stored_id)]],
            fields=["id"],
            limit=1,
        )
        if rows:
            return int(rows[0]["id"])

    rows = client.search_read(
        "hr.contract",
        [
            ["employee_id", "=", employee_odoo_id],
            ["date_start", "=", start_date],
        ],
        fields=["id", "employee_id", "date_start"],
        limit=2,
    )
    if len(rows) > 1:
        raise OdooContractSyncConflict(
            "Multiple Odoo contracts match the employee and start date."
        )
    if not rows:
        return None
    return int(rows[0]["id"])


def sync_contract_now(
    db: Session,
    *,
    employee_id: str,
    client=None,
) -> dict:
    """Synchronize one durable employee contract outbox row immediately."""

    sync = require_contract_sync(db, employee_id)
    transport = client or integration.build_odoo_client()
    employee_odoo_id = _employee_odoo_id(db, employee_id)

    sync.attempt_count = int(sync.attempt_count or 0) + 1
    sync.status = "PENDING"
    sync.last_error = None
    db.commit()
    db.refresh(sync)

    try:
        payload = dict(sync.payload or {})
        values, resolved = build_hr_contract_values(
            transport,
            payload,
            employee_odoo_id=employee_odoo_id,
        )
        start_date = str((payload.get("contract") or {}).get("start_date") or "").strip()
        existing_id = _find_existing_contract_id(
            transport,
            sync=sync,
            employee_odoo_id=employee_odoo_id,
            start_date=start_date,
        )
        if existing_id is None:
            odoo_id = transport.create("hr.contract", values)
            action = "CREATED"
        else:
            transport.write("hr.contract", [existing_id], values)
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
    except (
        OdooContractDeliveryError,
        OdooContractDependencyError,
        OdooContractSyncConflict,
        OdooClientError,
    ) as exc:
        sync.status = "FAILED"
        sync.last_error = str(exc)
        sync.synced_at = None
        db.commit()
        raise OdooContractDeliveryError(str(exc)) from exc
    except Exception as exc:
        sync.status = "FAILED"
        sync.last_error = "ODOO_CONTRACT_SYNC_FAILED"
        sync.synced_at = None
        db.commit()
        raise OdooContractDeliveryError("ODOO_CONTRACT_SYNC_FAILED") from exc
