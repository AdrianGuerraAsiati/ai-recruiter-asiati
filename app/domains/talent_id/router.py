"""HTTP routes for Talent ID administration and kiosk devices."""

from botocore.exceptions import ClientError
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    UploadFile,
)
from sqlalchemy.orm import Session

from app.config import get_talent_id_biometric_settings
from app.deps import get_db, require_permission
from app.domains.talent_id import biometrics, service
from app.domains.talent_id.schemas import (
    ConfigureEmployeeAttendanceRequest,
    CreateScheduleRequest,
    CreateSiteRequest,
    ProvisionKioskRequest,
)
from app.infrastructure.talent_id_rekognition import (
    FaceAssociationError,
    FaceNotDetectedError,
    RekognitionBiometricProvider,
    get_rekognition_client,
)


MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png"}

router = APIRouter(prefix="/api/talent-id", tags=["talent-id"])
kiosk_router = APIRouter(prefix="/v1/kiosk", tags=["talent-id-kiosk"])


def get_biometric_provider() -> RekognitionBiometricProvider:
    settings = get_talent_id_biometric_settings()
    if not settings.collection_id:
        raise HTTPException(
            status_code=503,
            detail="Talent ID biometrics are not configured.",
        )
    return RekognitionBiometricProvider(
        client=get_rekognition_client(),
        collection_id=settings.collection_id,
        association_threshold=settings.association_threshold,
    )


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


async def _read_image(image: UploadFile) -> bytes:
    if image.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=415,
            detail="La imagen debe ser JPEG o PNG.",
        )

    data = await image.read(MAX_IMAGE_BYTES + 1)
    if not data:
        raise HTTPException(status_code=422, detail="La imagen está vacía.")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail="La imagen excede el límite de 5 MB.",
        )
    return data


def _attendance_response(event, *, created: bool) -> dict:
    return {
        "id": event.id,
        "employee_id": event.employee_id,
        "site_id": event.site_id,
        "device_id": event.device_id,
        "event_type": event.event_type.lower(),
        "method": event.method.lower(),
        "occurred_at": event.occurred_at.isoformat(),
        "recognition_confidence": event.recognition_confidence,
        "created": created,
    }


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


@router.get("/employees/{employee_id}/attendance")
def get_employee_attendance(
    employee_id: str,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("talent_id.read")),
):
    try:
        service.get_employee(db, employee_id)
        settings = service.get_employee_attendance_settings(db, employee_id)
    except service.TalentIdNotFound:
        return {
            "employee_id": employee_id,
            "configured": False,
            "site_id": None,
            "schedule_id": None,
            "attendance_eligible": False,
        }

    return {
        "employee_id": settings.employee_id,
        "configured": True,
        "site_id": settings.site_id,
        "schedule_id": settings.schedule_id,
        "attendance_eligible": bool(settings.attendance_eligible),
    }


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


@router.get("/employees/{employee_id}/biometrics")
def get_employee_biometrics(
    employee_id: str,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("talent_id.read")),
):
    try:
        service.get_employee(db, employee_id)
    except Exception as exc:
        return _translate(exc)

    enrollment = biometrics.get_employee_enrollment(db, employee_id)
    if enrollment is None:
        return {
            "employee_id": employee_id,
            "enrolled": False,
            "provider": None,
            "face_count": 0,
            "active": False,
            "enrolled_at": None,
        }

    return {
        "employee_id": enrollment.employee_id,
        "enrolled": True,
        "provider": enrollment.provider,
        "face_count": int(enrollment.face_count or 0),
        "active": bool(enrollment.active),
        "enrolled_at": enrollment.enrolled_at.isoformat(),
    }


@router.post("/employees/{employee_id}/biometrics/enroll")
async def enroll_employee_biometrics(
    employee_id: str,
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("talent_id.manage")),
    provider: RekognitionBiometricProvider = Depends(get_biometric_provider),
):
    image_bytes = await _read_image(image)
    try:
        enrollment = biometrics.enroll_employee(
            db,
            provider=provider,
            employee_id=employee_id,
            image_bytes=image_bytes,
        )
    except biometrics.BiometricEmployeeNotAllowed as exc:
        raise HTTPException(
            status_code=403,
            detail="Empleado no habilitado para enrolamiento biométrico.",
        ) from exc
    except (FaceNotDetectedError, FaceAssociationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ClientError as exc:
        raise HTTPException(
            status_code=502,
            detail="El proveedor biométrico no respondió correctamente.",
        ) from exc

    return {
        "employee_id": enrollment.employee_id,
        "provider": enrollment.provider,
        "face_count": enrollment.face_count,
        "active": bool(enrollment.active),
        "enrolled_at": enrollment.enrolled_at.isoformat(),
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
    except service.InvalidKioskCredentials as exc:
        raise HTTPException(
            status_code=401,
            detail="Credenciales de dispositivo inválidas.",
        ) from exc
    except Exception as exc:
        return _translate(exc)

    return {
        "device": service.kiosk_payload(device),
        "site_name": site.name,
        "site_timezone": site.timezone,
    }


@kiosk_router.post("/recognize")
async def recognize_and_record_attendance(
    image: UploadFile = File(...),
    event_type: str = Form(...),
    x_device_id: str = Header(alias="X-Device-Id"),
    x_device_secret: str = Header(alias="X-Device-Secret"),
    idempotency_key: str = Header(
        alias="Idempotency-Key",
        min_length=8,
        max_length=80,
    ),
    db: Session = Depends(get_db),
    provider: RekognitionBiometricProvider = Depends(get_biometric_provider),
):
    try:
        device = service.authenticate_kiosk(
            db,
            device_id=x_device_id,
            secret=x_device_secret,
        )
    except service.InvalidKioskCredentials as exc:
        raise HTTPException(
            status_code=401,
            detail="Credenciales de dispositivo inválidas.",
        ) from exc

    normalized_event = event_type.strip().upper()
    if normalized_event not in {"CHECK_IN", "CHECK_OUT"}:
        raise HTTPException(status_code=422, detail="Tipo de marcación inválido.")

    namespaced_key = f"{device.id}:{idempotency_key.strip()}"
    existing = service.get_attendance_by_idempotency_key(db, namespaced_key)
    if existing is not None:
        if (
            existing.device_id != device.id
            or existing.event_type != normalized_event
        ):
            raise HTTPException(
                status_code=409,
                detail="Conflicto de Idempotency-Key.",
            )
        employee = service.get_employee(db, existing.employee_id)
        return {
            "employee_id": employee.id,
            "display_name": service.employee_display_name(employee),
            "similarity": existing.recognition_confidence or 0.0,
            "attendance": _attendance_response(existing, created=False),
        }

    image_bytes = await _read_image(image)
    settings = get_talent_id_biometric_settings()
    try:
        recognized = biometrics.recognize_employee(
            db,
            provider=provider,
            image_bytes=image_bytes,
            match_threshold=settings.match_threshold,
        )
    except ClientError as exc:
        raise HTTPException(
            status_code=502,
            detail="El proveedor biométrico no respondió correctamente.",
        ) from exc

    if recognized is None:
        raise HTTPException(
            status_code=404,
            detail="No se reconoció el rostro de un empleado habilitado.",
        )

    try:
        event, created = service.record_attendance(
            db,
            employee_id=recognized.employee_id,
            site_id=device.site_id,
            device_id=device.id,
            event_type=normalized_event,
            method="FACE",
            idempotency_key=namespaced_key,
            recognition_confidence=recognized.similarity,
        )
    except Exception as exc:
        return _translate(exc)

    return {
        "employee_id": recognized.employee_id,
        "display_name": recognized.display_name,
        "similarity": recognized.similarity,
        "attendance": _attendance_response(event, created=created),
    }
