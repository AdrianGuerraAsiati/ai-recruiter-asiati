"""HTTP endpoints for explicit Odoo synchronization actions."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_db, require_permission
from app.domains.odoo_sync import applicant_delivery, employee_delivery, integration


router = APIRouter(prefix="/api/odoo", tags=["odoo"])


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



@router.post("/applications/{application_id}/sync")
def sync_applicant_to_odoo(
    application_id: str,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("candidates.manage")),
):
    try:
        return applicant_delivery.sync_applicant_now(
            db,
            application_id=application_id,
        )
    except applicant_delivery.OdooApplicantSyncNotFound:
        raise HTTPException(
            status_code=404,
            detail="La postulacion no tiene una sincronizacion Odoo preparada.",
        )
    except (integration.OdooDisabled, integration.OdooNotConfigured) as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except applicant_delivery.OdooApplicantDeliveryError:
        raise HTTPException(
            status_code=502,
            detail="No fue posible sincronizar la postulacion con Odoo.",
        )
