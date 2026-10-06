"""Employee administration HTTP routes."""

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.access_control import ADMIN, EMPLOYEE
from app.deps import get_db, require_permission
from app.domains.employees import service
from app.domains.odoo_sync import employee_delivery, integration
from app.domains.employees.schemas import (
    CreateEmployeeRequest,
    SetEmployeeRoleRequest,
    SetEmployeeStatusRequest,
    SetEmployeeUsernameRequest,
    UpdateEmployeeRequest,
)
from app.domains.training import service as training_service


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/employees", tags=["employees"])


def _enforce_assignable_role(_principal: dict, role_code: str) -> None:
    if role_code not in {EMPLOYEE, ADMIN}:
        raise HTTPException(
            status_code=422,
            detail="Rol de empleado no valido.",
        )


def _enforce_not_self(principal: dict, employee_id: str) -> None:
    profile = principal.get("profile") or {}
    if profile.get("id") == employee_id:
        raise HTTPException(
            status_code=409,
            detail="No puedes modificar tu propio rol o estado desde esta operacion.",
        )


def _ensure_automatic_onboarding_for_all(
    db: Session,
    *,
    created_by_sub: str | None,
) -> None:
    try:
        course = training_service.ensure_published_asiati_onboarding(
            db,
            created_by_sub=created_by_sub or "system:employee-directory",
        )
        training_service.ensure_asiati_onboarding_for_active_employees(
            db,
            course=course,
            created_by_sub=created_by_sub,
        )
    except Exception:
        db.rollback()
        logger.exception("Automatic ASIATI onboarding backfill failed")


def _ensure_automatic_onboarding(
    db: Session,
    *,
    employee_id: str,
    created_by_sub: str | None,
) -> None:
    try:
        training_service.ensure_employee_asiati_onboarding(
            db,
            employee_id=employee_id,
            created_by_sub=created_by_sub,
        )
    except Exception:
        db.rollback()
        logger.exception(
            "Automatic ASIATI onboarding sync failed for employee %s",
            employee_id,
        )


def _sync_created_employee_to_odoo(db: Session, employee) -> dict:
    sync = employee_delivery.ensure_direct_employee_sync(
        db,
        employee=employee,
    )
    try:
        return employee_delivery.sync_employee_now(
            db,
            employee_id=employee.id,
        )
    except (integration.OdooDisabled, integration.OdooNotConfigured) as exc:
        return {
            "employee_id": employee.id,
            "status": "PENDING",
            "attempt_count": sync.attempt_count,
            "odoo_record_id": sync.odoo_record_id,
            "action": "DEFERRED",
            "detail": str(exc),
        }
    except employee_delivery.OdooEmployeeDeliveryError as exc:
        return {
            "employee_id": employee.id,
            "status": "FAILED",
            "attempt_count": sync.attempt_count,
            "odoo_record_id": sync.odoo_record_id,
            "action": "RETRY_REQUIRED",
            "detail": str(exc),
        }


def _translate_service_error(exc: Exception):
    if isinstance(exc, service.EmployeeNotFound):
        raise HTTPException(status_code=404, detail="Empleado no encontrado.")
    if isinstance(exc, service.EmployeeAlreadyExists):
        raise HTTPException(
            status_code=409,
            detail="Ya existe un usuario con este correo.",
        )
    if isinstance(exc, service.EmployeeUsernameExists):
        raise HTTPException(status_code=409, detail="Ese usuario ya existe.")
    if isinstance(exc, service.EmployeeUsernameInvalid):
        raise HTTPException(status_code=422, detail="El usuario no tiene un formato valido.")
    if isinstance(exc, service.EmployeeStateError):
        raise HTTPException(status_code=422, detail="Estado de empleado no valido.")
    if isinstance(exc, service.EmployeeIdentityError):
        raise HTTPException(
            status_code=502,
            detail="Cognito no devolvio una identidad valida para el empleado.",
        )
    if isinstance(exc, service.EmployeeProvisioningError):
        raise HTTPException(
            status_code=502,
            detail="No fue posible sincronizar el empleado con Cognito.",
        )
    raise exc


@router.get("")
def list_employees(
    q: str = Query("", max_length=120),
    status: Literal["ACTIVE", "DISABLED"] | None = Query(None),
    onboarding_status: Literal[
        "NOT_REQUIRED",
        "PENDING",
        "IN_PROGRESS",
        "COMPLETED",
    ] | None = Query(None),
    db: Session = Depends(get_db),
    principal: dict = Depends(require_permission("employees.read")),
):
    _ensure_automatic_onboarding_for_all(
        db,
        created_by_sub=principal.get("sub"),
    )
    employees = service.list_employees(
        db,
        q=q,
        status=status,
        onboarding_status=onboarding_status,
    )
    return {
        "items": [service.employee_payload(db, employee) for employee in employees],
        "total": len(employees),
    }


@router.get("/summary")
def get_employee_summary(
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("employees.read")),
):
    return service.employee_summary(db)


@router.get("/credentials/availability")
def check_username_availability(
    username: str = Query(..., min_length=3, max_length=40),
    exclude_employee_id: str | None = Query(None),
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("employees.credentials.manage")),
):
    try:
        normalized, available = service.username_available(
            db,
            username=username,
            exclude_employee_id=exclude_employee_id,
        )
        return {"username": normalized, "available": available}
    except Exception as exc:
        _translate_service_error(exc)


@router.get("/{employee_id}")
def get_employee(
    employee_id: str,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("employees.read")),
):
    try:
        employee = service.require_employee(db, employee_id)
        return service.employee_payload(db, employee)
    except Exception as exc:
        _translate_service_error(exc)


@router.post("", status_code=201)
def create_employee(
    body: CreateEmployeeRequest,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_permission("employees.create")),
):
    _enforce_assignable_role(principal, body.role)
    try:
        employee, temporary_password = service.provision_employee(
            db,
            username=body.username,
            email=body.email,
            first_name=body.first_name,
            last_name=body.last_name,
            job_title=body.job_title,
            department=body.department,
            hire_date=body.hire_date,
            role_code=body.role,
            created_by_sub=principal.get("sub"),
        )
        _ensure_automatic_onboarding(
            db,
            employee_id=employee.id,
            created_by_sub=principal.get("sub"),
        )
        odoo_sync = _sync_created_employee_to_odoo(db, employee)
        db.refresh(employee)
        return {
            "employee": service.employee_payload(db, employee),
            "credentials": {
                "username": employee.login_username,
                "temporary_password": temporary_password,
                "must_change_password": True,
            },
            "odoo_sync": odoo_sync,
        }
    except Exception as exc:
        _translate_service_error(exc)


@router.put("/{employee_id}/credentials/username")
def update_employee_username(
    employee_id: str,
    body: SetEmployeeUsernameRequest,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("employees.credentials.manage")),
):
    try:
        employee = service.set_employee_username(
            db,
            employee_id,
            username=body.username,
        )
        return service.employee_payload(db, employee)
    except Exception as exc:
        _translate_service_error(exc)


@router.post("/{employee_id}/credentials/reset-password")
def reset_employee_password(
    employee_id: str,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("employees.credentials.manage")),
):
    try:
        employee, temporary_password = service.reset_employee_temporary_password(
            db,
            employee_id,
        )
        return {
            "employee": service.employee_payload(db, employee),
            "credentials": {
                "username": employee.login_username,
                "temporary_password": temporary_password,
                "must_change_password": True,
            },
        }
    except Exception as exc:
        _translate_service_error(exc)


@router.put("/{employee_id}")
def update_employee(
    employee_id: str,
    body: UpdateEmployeeRequest,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("employees.update")),
):
    try:
        employee = service.update_employee(
            db,
            employee_id,
            changes=body.model_dump(exclude_unset=True),
        )
        _ensure_automatic_onboarding(
            db,
            employee_id=employee.id,
            created_by_sub=_principal.get("sub"),
        )
        return service.employee_payload(db, employee)
    except Exception as exc:
        _translate_service_error(exc)


@router.put("/{employee_id}/status")
def update_employee_status(
    employee_id: str,
    body: SetEmployeeStatusRequest,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_permission("employees.disable")),
):
    _enforce_not_self(principal, employee_id)
    try:
        employee = service.set_employee_status(
            db,
            employee_id,
            status=body.status,
        )
        if body.status == "ACTIVE":
            _ensure_automatic_onboarding(
                db,
                employee_id=employee.id,
                created_by_sub=principal.get("sub"),
            )
        return service.employee_payload(db, employee)
    except Exception as exc:
        _translate_service_error(exc)


@router.put("/{employee_id}/role")
def update_employee_role(
    employee_id: str,
    body: SetEmployeeRoleRequest,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_permission("employees.roles.manage")),
):
    _enforce_not_self(principal, employee_id)
    _enforce_assignable_role(principal, body.role)
    try:
        employee = service.set_employee_role(
            db,
            employee_id,
            role_code=body.role,
            assigned_by_sub=principal.get("sub"),
        )
        return service.employee_payload(db, employee)
    except Exception as exc:
        _translate_service_error(exc)
