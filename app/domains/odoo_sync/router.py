"""HTTP endpoints for explicit Odoo synchronization actions."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_db, require_permission
from app.domains.odoo_sync import (
    applicant_import,
    contract_delivery,
    employee_delivery,
    employee_import,
    integration,
    job_delivery,
)
from app.integrations.odoo.client import OdooClientError


router = APIRouter(prefix="/api/odoo", tags=["odoo"])


@router.get("/diagnostics")
def odoo_readonly_diagnostics(
    _principal: dict = Depends(require_permission("employees.update")),
):
    """Authenticate and inspect relevant Odoo models without writing data."""
    status = integration.connection_status()
    try:
        client = integration.build_odoo_client()
        health = client.healthcheck()
    except (integration.OdooDisabled, integration.OdooNotConfigured, OdooClientError) as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    models = {}
    for model in (
        "hr.employee",
        "hr.job",
        "hr.applicant",
        "hr.contract",
        "ir.attachment",
        "sign.request",
        "sign.template",
    ):
        try:
            fields = client.fields_get(model)
            models[model] = {
                "available": True,
                "field_count": len(fields),
                "fields": sorted(fields.keys()),
            }
        except OdooClientError:
            models[model] = {"available": False}

    return {"connection": status, "health": health, "models": models, "read_only": True}


@router.post("/jobs/sync")
def sync_jobs_to_odoo(
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("jobs.manage")),
):
    """Reconcile all Talent vacancies with Odoo using ACTIVE/PAUSED semantics."""
    try:
        return job_delivery.sync_all_jobs_now(db)
    except (integration.OdooDisabled, integration.OdooNotConfigured) as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except (job_delivery.OdooJobDeliveryError, OdooClientError) as exc:
        raise HTTPException(
            status_code=502,
            detail=f"No fue posible actualizar las vacantes en Odoo: {exc}",
        )


@router.post("/applicants/import")
def import_applicants_from_odoo(
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("candidates.manage")),
):
    """Incrementally import Odoo Recruitment applicants and their resumes."""
    try:
        return applicant_import.sync_applicants_from_odoo(db)
    except (integration.OdooDisabled, integration.OdooNotConfigured) as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except applicant_import.OdooApplicantImportError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"No fue posible importar los candidatos desde Odoo: {exc}",
        )


@router.post("/employees/import")
def import_employees_from_odoo(
    db: Session = Depends(get_db),
    principal: dict = Depends(require_permission("employees.create")),
):
    """Import every Odoo hr.employee record without creating Cognito access."""
    try:
        return employee_import.sync_employees_from_odoo(
            db,
            actor_sub=principal.get("sub"),
        )
    except (integration.OdooDisabled, integration.OdooNotConfigured) as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except employee_import.OdooEmployeeImportError:
        raise HTTPException(
            status_code=502,
            detail="No fue posible importar los empleados desde Odoo.",
        )


@router.post("/employees/{employee_id}/sync")
def sync_employee_to_odoo(
    employee_id: str,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("employees.update")),
):
    try:
        return employee_delivery.sync_employee_now(
            db,
            employee_id=employee_id,
        )
    except employee_delivery.OdooEmployeeSyncNotFound:
        raise HTTPException(
            status_code=404,
            detail="El empleado no tiene una sincronizacion Odoo preparada.",
        )
    except (integration.OdooDisabled, integration.OdooNotConfigured) as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except employee_delivery.OdooEmployeeDeliveryError:
        raise HTTPException(
            status_code=502,
            detail="No fue posible sincronizar el empleado con Odoo.",
        )



@router.post("/employees/{employee_id}/contract/sync")
def sync_employee_contract_to_odoo(
    employee_id: str,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("employees.update")),
):
    try:
        return contract_delivery.sync_contract_now(
            db,
            employee_id=employee_id,
        )
    except contract_delivery.OdooContractSyncNotFound:
        raise HTTPException(
            status_code=404,
            detail="El empleado no tiene un contrato Odoo preparado.",
        )
    except contract_delivery.OdooContractDependencyError:
        raise HTTPException(
            status_code=409,
            detail="Sincroniza primero el empleado con Odoo.",
        )
    except (integration.OdooDisabled, integration.OdooNotConfigured) as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except contract_delivery.OdooContractDeliveryError:
        raise HTTPException(
            status_code=502,
            detail="No fue posible sincronizar el contrato con Odoo.",
        )
