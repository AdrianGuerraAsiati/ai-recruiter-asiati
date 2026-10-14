"""Safe, side-effect-free contract-termination validation and planning.

Contract closure must be performed by a dedicated Odoo adapter after a staging
integration test. This module deliberately never writes to Odoo or Cognito.
"""
from dataclasses import dataclass
from datetime import date
from enum import Enum


class TerminationError(ValueError):
    """Invalid or unsafe employment termination request."""


class TerminationReason(str, Enum):
    RESIGNATION = "RESIGNATION"
    CONTRACT_END = "CONTRACT_END"
    DISMISSAL = "DISMISSAL"
    MUTUAL_AGREEMENT = "MUTUAL_AGREEMENT"
    OTHER = "OTHER"


@dataclass(frozen=True)
class TerminationPlan:
    employee_id: str
    odoo_employee_id: str
    effective_date: date
    reason: TerminationReason
    notes: str
    steps: tuple[str, ...] = (
        "verify_odoo_employee",
        "identify_active_contracts",
        "review_contract_end_date",
        "close_contracts_in_odoo",
        "archive_odoo_employee",
        "disable_cognito_access",
        "record_audit_and_reconciliation",
    )


def build_termination_plan(
    *,
    employee_id: str,
    odoo_employee_id: str | None,
    effective_date: date,
    reason: TerminationReason,
    notes: str,
    already_terminated: bool = False,
    today: date | None = None,
) -> TerminationPlan:
    """Validate a request without altering production records.

    No implicit removal, no unlinked Odoo write, and no future-dated closure.
    The write workflow must additionally verify permissions, contract ownership,
    company, concurrency, idempotency and Odoo acknowledgements.
    """
    if not employee_id or not employee_id.strip():
        raise TerminationError("Identificador de empleado obligatorio.")
    if not odoo_employee_id or not str(odoo_employee_id).strip():
        raise TerminationError("Primero se debe vincular el empleado con Odoo.")
    if already_terminated:
        raise TerminationError("El empleado ya figura como retirado.")
    if not isinstance(effective_date, date) or isinstance(effective_date, __import__("datetime").datetime):
        raise TerminationError("Fecha de retiro inválida.")
    if effective_date > (today or date.today()):
        raise TerminationError("No se puede finalizar anticipadamente un contrato futuro.")
    if not isinstance(reason, TerminationReason):
        raise TerminationError("Motivo de retiro inválido.")
    if not notes or not notes.strip() or len(notes.strip()) < 10:
        raise TerminationError("Se requiere una justificación de al menos diez caracteres.")
    if len(notes) > 2000:
        raise TerminationError("La justificación excede el máximo permitido.")
    return TerminationPlan(
        employee_id=employee_id.strip(),
        odoo_employee_id=str(odoo_employee_id).strip(),
        effective_date=effective_date,
        reason=reason,
        notes=notes.strip(),
    )
