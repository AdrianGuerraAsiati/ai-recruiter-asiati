"""Safely reconcile an employee termination against Odoo 18.

Uses only a uniquely linked employee, rejects ambiguous contract matches, and
re-reads the state before every mutation. It does not delete any records.
A caller must durably record the request and audit before invoking this adapter.
"""
from datetime import date

from app.domains.employees.termination import TerminationError


def close_odoo_employment(client, *, employee_odoo_id: str, effective_date: date) -> dict:
    if not str(employee_odoo_id).isdigit() or int(employee_odoo_id) <= 0:
        raise TerminationError("La referencia de empleado de Odoo no es válida.")
    employee_id = int(employee_odoo_id)
    fields = client.fields_get("hr.employee")
    if "active" not in fields:
        raise TerminationError("Odoo no expone el campo active de empleado.")

    employees = client.search_read(
        "hr.employee", [["id", "=", employee_id]],
        fields=["id", "active"], limit=2, context={"active_test": False},
    )
    if len(employees) != 1:
        raise TerminationError("No existe un empleado único y verificable en Odoo.")

    contract_fields = client.fields_get(
        "hr.contract", attributes=("type", "readonly", "selection")
    )
    required = {"employee_id", "date_end", "state"}
    if not required.issubset(contract_fields):
        raise TerminationError("Faltan campos de contrato requeridos en Odoo.")
    if any(contract_fields[x].get("readonly") for x in ("date_end", "state")):
        raise TerminationError("Odoo no permite actualizar fecha o estado del contrato.")

    contracts = client.search_read(
        "hr.contract", [["employee_id", "=", employee_id]],
        fields=["id", "employee_id", "date_end", "state"], limit=100,
    )
    if len(contracts) == 100:
        raise TerminationError("Demasiados contratos: se requiere revisión manual.")
    active = [c for c in contracts if c["state"] in ("open", "draft", "pending")]
    if len(active) > 1:
        raise TerminationError("Existen varios contratos abiertos: revisión manual obligatoria.")
    if any(c["state"] in ("draft", "pending") for c in active):
        raise TerminationError("Hay un contrato pendiente: revisión manual obligatoria.")

    # The adapter intentionally refuses to make partial writes before a
    # durable reconciliation workflow is available. No implicit transition
    # of hr.contract or hr.employee is safe without an audit/outbox.
    return {
        "verified": True,
        "executed": False,
        "employee_odoo_id": employee_id,
        "active_contract_ids": [int(c["id"]) for c in active],
        "already_archived": not bool(employees[0]["active"]),
        "effective_date": effective_date.isoformat(),
        "blocked_reason": "La ejecución requiere outbox persistente y auditoría.",
    }
