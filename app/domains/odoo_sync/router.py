"""HTTP endpoints for explicit Odoo synchronization actions."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_db, require_permission
from app.domains.odoo_sync import employee_delivery, integration
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
