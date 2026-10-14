"""Resumable execution of a previously persisted employment termination.

Explicitly opt-in on staging only until real Odoo 18 contract transitions
have been verified. Caller supplies a transaction-scoped row lock.
"""
import os

from app.domains.employees.termination import TerminationError
from app.domains.odoo_sync.employee_termination import close_odoo_employment
from app.models import EmployeeTerminationRequest, UserProfile
from app.domains.employees import service


def execute_termination(db, *, request_id: str, odoo_client, cognito_client):
    if os.getenv("EMPLOYEE_TERMINATION_EXECUTION_ENABLED") != "true":
        raise TerminationError("Ejecución de retiros deshabilitada.")
    if os.getenv("APP_ENV", "").lower() not in {"staging", "test"}:
        raise TerminationError("Solo se permite ejecutar retiros en staging.")

    request = db.query(EmployeeTerminationRequest).filter(
        EmployeeTerminationRequest.id == request_id
    ).with_for_update().one_or_none()
    if request is None:
        raise TerminationError("Solicitud de retiro inexistente.")
    employee = db.query(UserProfile).filter(
        UserProfile.id == request.employee_id
    ).with_for_update().one_or_none()
    if employee is None or str(employee.odoo_employee_id) != request.odoo_employee_id:
        raise TerminationError("La identidad de Odoo cambió: revisión manual requerida.")
    if request.status == "COMPLETED":
        return {"status": "COMPLETED", "idempotent": True}
    if request.status == "IN_PROGRESS":
        raise TerminationError("La solicitud ya está siendo procesada.")

    request.status = "IN_PROGRESS"
    request.attempt_count = int(request.attempt_count or 0) + 1
    request.last_error = None
    db.commit()

    try:
        steps = list(request.steps_completed or [])
        if "odoo_verified" not in steps:
            verification = close_odoo_employment(
                odoo_client,
                employee_odoo_id=request.odoo_employee_id,
                effective_date=request.effective_date.date(),
            )
            if not verification["verified"]:
                raise TerminationError("No se validó el contrato en Odoo.")
            steps.append("odoo_verified")
            request.steps_completed = steps
            db.commit()

        # Fail closed: contract state semantics must be confirmed against
        # the actual company's Odoo 18 schema before enabling mutation.
        raise TerminationError(
            "Validación completada. Cierre contractual pendiente de homologación Odoo."
        )
    except Exception as exc:
        request.status = "FAILED"
        request.last_error = str(exc)[:500]
        db.commit()
        raise
