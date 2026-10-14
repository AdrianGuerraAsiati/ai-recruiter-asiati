"""Conservative, idempotent Odoo 18 contract closure.

Call after persisting a termination request. Odoo writes are retried only after
re-reading current remote state, never by creating/deleting employee records.
"""
from datetime import date

from app.domains.employees.termination import TerminationError
from app.domains.odoo_sync.employee_termination import close_odoo_employment


def _one_employee(client, employee_id):
    rows = client.search_read("hr.employee", [["id", "=", employee_id]],
                              fields=["id", "active"], limit=2)
    if len(rows) != 1:
        raise TerminationError("El empleado de Odoo no es único o no existe.")
    return rows[0]


def _contracts(client, employee_id):
    rows = client.search_read("hr.contract", [["employee_id", "=", employee_id]],
                              fields=["id", "employee_id", "state", "date_end"], limit=100)
    if len(rows) == 100:
        raise TerminationError("Se requiere revisar manualmente el historial contractual.")
    return rows


def _verify_owner(row, employee_id):
    value = row.get("employee_id")
    owner = value[0] if isinstance(value, (list, tuple)) else value
    if str(owner) != str(employee_id):
        raise TerminationError("El contrato pertenece a otro empleado.")


def close_contract_and_archive(client, *, employee_odoo_id: str, effective_date: date) -> dict:
    """Close a unique open contract, then archive the employee.

    A failed network acknowledgement may leave Odoo changed. Every retry reads
    Odoo first and verifies the desired state before attempting another write.
    """
    inspection = close_odoo_employment(
        client, employee_odoo_id=employee_odoo_id, effective_date=effective_date
    )
    employee_id = inspection["employee_odoo_id"]
    metadata = client.fields_get(
        "hr.contract", attributes=("type", "readonly", "selection")
    )
    choices = {
        str(entry[0])
        for entry in (metadata.get("state", {}).get("selection") or [])
        if isinstance(entry, (list, tuple)) and entry
    }
    if "close" not in choices:
        raise TerminationError("Odoo no confirma el estado close para hr.contract.")

    contracts = _contracts(client, employee_id)
    for contract in contracts:
        _verify_owner(contract, employee_id)
    open_contracts = [c for c in contracts if c.get("state") == "open"]
    if len(open_contracts) > 1:
        raise TerminationError("Más de un contrato abierto; revisión manual.")
    if any(c.get("state") in {"draft", "pending"} for c in contracts):
        raise TerminationError("Existen contratos pendientes; revisión manual.")

    if open_contracts:
        contract = open_contracts[0]
        original_end = contract.get("date_end")
        if original_end and str(original_end) < effective_date.isoformat():
            raise TerminationError("La fecha solicitada es posterior al fin contractual existente.")
        client.write("hr.contract", [int(contract["id"])], {
            "date_end": effective_date.isoformat(), "state": "close",
        })

    verified_contracts = _contracts(client, employee_id)
    for contract in verified_contracts:
        _verify_owner(contract, employee_id)
    if any(c.get("state") in {"open", "draft", "pending"} for c in verified_contracts):
        raise TerminationError("Odoo no confirmó el cierre de todos los contratos.")
    if open_contracts:
        closed = [c for c in verified_contracts if int(c["id"]) == int(open_contracts[0]["id"])]
        if len(closed) != 1 or closed[0].get("state") != "close" or str(closed[0].get("date_end")) != effective_date.isoformat():
            raise TerminationError("Odoo no confirmó la fecha y estado de terminación.")

    if _one_employee(client, employee_id).get("active"):
        client.write("hr.employee", [employee_id], {"active": False})
    if _one_employee(client, employee_id).get("active"):
        raise TerminationError("Odoo no confirmó el archivado del empleado.")

    return {
        "employee_odoo_id": employee_id,
        "contract_id": int(open_contracts[0]["id"]) if open_contracts else None,
        "odoo_closed": True,
        "odoo_archived": True,
    }
