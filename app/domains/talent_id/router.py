"""HTTP routes for Talent ID administration and kiosk devices."""

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_db, require_permission
from app.domains.talent_id import service
from app.domains.talent_id.schemas import (
    ConfigureEmployeeAttendanceRequest,
    CreateScheduleRequest,
    CreateSiteRequest,
    ProvisionKioskRequest,
)


router = APIRouter(prefix="/api/talent-id", tags=["talent-id"])
kiosk_router = APIRouter(prefix="/v1/kiosk", tags=["talent-id-kiosk"])


def _translate(exc: Exception):
    if isinstance(exc, service.TalentIdNotFound):
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, service.EmployeeNotEligibleForAttendance):
        raise HTTPException(
            status_code=409,
            detail="El empleado no está habilitado para marcar asistencia.",
        )
    if isinstance(exc, service.AttendanceSiteMismatch):
        raise HTTPException(
            status_code=409,
            detail="La sede de la marcación no coincide con la del empleado.",
        )
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=422, detail=str(exc))
    raise exc


@router.get("/sites")
def list_sites(
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("talent_id.read")),
):
    items = [service.site_payload(site) for site in service.list_sites(db)]
    return {"items": items, "total": len(items)}


@router.post("/sites", status_code=201)
def create_site(
    body: CreateSiteRequest,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("talent_id.manage")),
):
    try:
        site = service.create_site(
            db,
            name=body.name,
            code=body.code,
            timezone_name=body.timezone,
        )
    except Exception as exc:
        return _translate(exc)
    return service.site_payload(site)


@router.get("/schedules")
def list_schedules(
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("talent_id.read")),
):
    items = [
        service.schedule_payload(schedule)
        for schedule in service.list_schedules(db)
    ]
    return {"items": items, "total": len(items)}


@router.post("/schedules", status_code=201)
def create_schedule(
    body: CreateScheduleRequest,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("talent_id.manage")),
):
    try:
        schedule = service.create_schedule(
            db,
            name=body.name,
            start_time=body.start_time,
            end_time=body.end_time,
            tolerance_minutes=body.tolerance_minutes,
        )
    except Exception as exc:
        return _translate(exc)
    return service.schedule_payload(schedule)


@router.put("/employees/{employee_id}/attendance")
def configure_employee_attendance(
    employee_id: str,
    body: ConfigureEmployeeAttendanceRequest,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("talent_id.manage")),
):
    try:
        settings = service.configure_employee_attendance(
            db,
            employee_id=employee_id,
            site_id=body.site_id,
            schedule_id=body.schedule_id,
            attendance_eligible=body.attendance_eligible,
        )
    except Exception as exc:
        return _translate(exc)

    return {
        "employee_id": settings.employee_id,
        "site_id": settings.site_id,
        "schedule_id": settings.schedule_id,
        "attendance_eligible": bool(settings.attendance_eligible),
    }


@router.get("/devices")
def list_devices(
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("talent_id.read")),
):
    items = [service.kiosk_payload(device) for device in service.list_kiosks(db)]
    return {"items": items, "total": len(items)}


@router.post("/devices", status_code=201)
def provision_device(
    body: ProvisionKioskRequest,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("talent_id.manage")),
):
    try:
        device, secret = service.provision_kiosk(
            db,
            site_id=body.site_id,
            name=body.name,
        )
    except Exception as exc:
        return _translate(exc)

    return {
        "device": service.kiosk_payload(device),
        "device_secret": secret,
        "secret_shown_once": True,
    }


@kiosk_router.get("/context")
def kiosk_context(
    x_device_id: str = Header(alias="X-Device-Id"),
    x_device_secret: str = Header(alias="X-Device-Secret"),
    db: Session = Depends(get_db),
):
    try:
        device = service.authenticate_kiosk(
            db,
            device_id=x_device_id,
            secret=x_device_secret,
        )
        site = service.get_site(db, device.site_id)
    except service.InvalidKioskCredentials:
        raise HTTPException(status_code=401, detail="Credenciales de dispositivo inválidas.")
    except Exception as exc:
        return _translate(exc)

    return {
        "device": service.kiosk_payload(device),
        "site_name": site.name,
        "site_timezone": site.timezone,
    }
