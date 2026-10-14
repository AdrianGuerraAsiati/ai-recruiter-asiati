"""Persist termination requests, not termination side effects.

Execution is deliberately separated from request creation to avoid fake success
when Odoo, Cognito or a worker is unavailable.
"""
import uuid
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.employees.termination import (
    TerminationError,
    TerminationReason,
    build_termination_plan,
)
from app.models import EmployeeTerminationRequest, UserProfile


def request_termination(
    db: Session,
    *,
    employee_id: str,
    effective_date,
    reason: TerminationReason,
    notes: str,
    actor_sub: str,
    idempotency_key: str,
) -> EmployeeTerminationRequest:
    if not actor_sub or not actor_sub.strip():
        raise TerminationError("Se requiere identificar al administrador.")
    if not idempotency_key or len(idempotency_key) > 128:
        raise TerminationError("Clave de idempotencia obligatoria.")

    # Locks the local employee row until the intent has been committed.
    profile = db.query(UserProfile).filter(UserProfile.id == employee_id).with_for_update().one_or_none()
    if profile is None:
        raise TerminationError("Empleado no encontrado.")
    existing = db.query(EmployeeTerminationRequest).filter(
        EmployeeTerminationRequest.employee_id == employee_id
    ).one_or_none()
    if existing:
        if existing.idempotency_key == idempotency_key:
            return existing
        raise TerminationError("Ya existe una solicitud de retiro para este empleado.")

    plan = build_termination_plan(
        employee_id=employee_id,
        odoo_employee_id=profile.odoo_employee_id,
        effective_date=effective_date,
        reason=reason,
        notes=notes,
    )
    request = EmployeeTerminationRequest(
        id=str(uuid.uuid4()),
        employee_id=plan.employee_id,
        odoo_employee_id=plan.odoo_employee_id,
        idempotency_key=idempotency_key,
        effective_date=datetime.combine(plan.effective_date, datetime.min.time()),
        reason=plan.reason.value,
        notes=plan.notes,
        requested_by_sub=actor_sub,
        status="PENDING",
        steps_completed=[],
    )
    db.add(request)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise TerminationError("Solicitud duplicada o concurrente; consulta el estado actual.") from exc
    db.refresh(request)
    return request


def termination_request_payload(request: EmployeeTerminationRequest) -> dict:
    return {
        "id": request.id,
        "employee_id": request.employee_id,
        "odoo_employee_id": request.odoo_employee_id,
        "effective_date": request.effective_date.date().isoformat(),
        "reason": request.reason,
        "notes": request.notes,
        "status": request.status,
        "executed": request.status == "COMPLETED",
        "steps_completed": list(request.steps_completed or []),
        "last_error": request.last_error,
        "created_at": request.created_at.isoformat() if request.created_at else None,
    }
