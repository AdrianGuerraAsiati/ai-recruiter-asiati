"""HTTP routes for Talent ID administration and kiosk devices."""

import logging
from datetime import date

from botocore.exceptions import ClientError
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from sqlalchemy.orm import Session

from app.config import (
    get_talent_id_biometric_settings,
    get_talent_id_consent_settings,
    get_talent_id_qr_settings,
)
from app.deps import get_current_principal, get_db, require_permission
from app.domains.talent_id import biometrics, consent, mobile_qr, reporting, service
from app.domains.talent_id.schemas import (
    ConfigureEmployeeAttendanceRequest,
    RegisterMobileDeviceRequest,
    KioskQrAttendanceRequest,
    IssueMobileQrRequest,
    ManualAttendanceRequest,
    CreateScheduleRequest,
    CreateSiteRequest,
    ProvisionKioskRequest,
    RequestBiometricConsentOtp,
    SignBiometricConsentRequest,
    UpdateKioskRequest,
)
from app.infrastructure.talent_id_consent_email import (
    ConsentEmailDeliveryError,
    MobileLinkEmailDeliveryError,
    send_consent_otp,
    send_mobile_link_otp,
)
from app.infrastructure.talent_id_rekognition import (
    FaceAssociationError,
    FaceNotDetectedError,
    RekognitionBiometricProvider,
    get_rekognition_client,
)


logger = logging.getLogger(__name__)

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



def _principal_employee_id(principal: dict) -> str:
    employee_id = str((principal.get("profile") or {}).get("id") or "").strip()
    if not employee_id:
        raise HTTPException(status_code=403, detail="Perfil de empleado no disponible.")
    return employee_id


def _consent_error(exc: Exception):
    if isinstance(exc, consent.ConsentOtpCooldown):
        raise HTTPException(status_code=429, detail=str(exc))
    if isinstance(exc, consent.ConsentOtpUnavailable):
        raise HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, ConsentEmailDeliveryError):
        raise HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, consent.ConsentOtpExpired):
        raise HTTPException(status_code=410, detail=str(exc))
    if isinstance(exc, consent.ConsentOtpLocked):
        raise HTTPException(status_code=429, detail=str(exc))
    if isinstance(exc, (consent.ConsentOtpInvalid, consent.ConsentStateError, ValueError)):
        raise HTTPException(status_code=422, detail=str(exc))
    raise exc


def _mobile_qr_error(exc: Exception):
    if isinstance(exc, mobile_qr.MobileLinkOtpCooldown):
        raise HTTPException(status_code=429, detail=str(exc))
    if isinstance(exc, mobile_qr.MobileLinkOtpUnavailable):
        raise HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, MobileLinkEmailDeliveryError):
        raise HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, mobile_qr.MobileLinkOtpExpired):
        raise HTTPException(status_code=410, detail=str(exc))
    if isinstance(exc, mobile_qr.MobileLinkOtpLocked):
        raise HTTPException(status_code=429, detail=str(exc))
    if isinstance(exc, mobile_qr.MobileLinkOtpInvalid):
        raise HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, mobile_qr.MobileDeviceNotFound):
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(
        exc,
        (
            mobile_qr.MobileDeviceSignatureInvalid,
            mobile_qr.MobileQrChallengeInvalid,
            mobile_qr.MobileQrTokenInvalid,
        ),
    ):
        raise HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, mobile_qr.MobileQrTokenExpired):
        raise HTTPException(status_code=410, detail=str(exc))
    if isinstance(exc, mobile_qr.MobileQrTokenUsed):
        raise HTTPException(status_code=409, detail=str(exc))
    return _translate(exc)


def _disable_biometrics_after_opt_out(db: Session, employee_id: str) -> None:
    enrollment = biometrics.get_employee_enrollment(db, employee_id)
    if enrollment is None or not enrollment.active:
        return

    provider_user_id = enrollment.provider_user_id
    biometrics.revoke_employee_enrollment(
        db,
        employee_id=employee_id,
    )

    settings = get_talent_id_biometric_settings()
    if not settings.collection_id:
        return

    try:
        provider = RekognitionBiometricProvider(
            client=get_rekognition_client(),
            collection_id=settings.collection_id,
            association_threshold=settings.association_threshold,
        )
        provider.delete_user(provider_user_id=provider_user_id)
    except Exception:
        # Consent revocation must remain effective even if provider cleanup
        # temporarily fails. Local recognition has already been disabled.
        logger.exception(
            "Provider cleanup failed after biometric consent opt-out for %s",
            employee_id,
        )


@router.get("/consent")
def get_my_biometric_consent(
    db: Session = Depends(get_db),
    principal: dict = Depends(get_current_principal),
):
    employee_id = _principal_employee_id(principal)
    try:
        return consent.consent_payload(db, employee_id, include_document=True)
    except Exception as exc:
        return _consent_error(exc)


@router.post("/consent/otp")
def request_my_biometric_consent_otp(
    body: RequestBiometricConsentOtp,
    db: Session = Depends(get_db),
    principal: dict = Depends(get_current_principal),
):
    employee_id = _principal_employee_id(principal)
    settings = get_talent_id_consent_settings()
    try:
        return consent.request_otp(
            db,
            employee_id=employee_id,
            decision=body.decision,
            expected_document_version=body.document_version,
            otp_secret=settings.otp_secret,
            ttl_seconds=settings.otp_ttl_seconds,
            cooldown_seconds=settings.otp_cooldown_seconds,
            max_attempts=settings.otp_max_attempts,
            send_otp=send_consent_otp,
        )
    except Exception as exc:
        return _consent_error(exc)


@router.post("/consent/sign")
def sign_my_biometric_consent(
    body: SignBiometricConsentRequest,
    request: Request,
    db: Session = Depends(get_db),
    principal: dict = Depends(get_current_principal),
):
    employee_id = _principal_employee_id(principal)
    settings = get_talent_id_consent_settings()
    client_ip = request.client.host if request.client else None
    evidence = {
        "auth_sub": principal.get("sub"),
        "ip_hash": consent.hash_evidence_value(settings.otp_secret, client_ip),
        "user_agent_hash": consent.hash_evidence_value(
            settings.otp_secret,
            request.headers.get("user-agent"),
        ),
    }
    try:
        event = consent.sign_decision(
            db,
            employee_id=employee_id,
            decision=body.decision,
            otp=body.otp,
            expected_document_version=body.document_version,
            otp_secret=settings.otp_secret,
            evidence=evidence,
        )
    except Exception as exc:
        return _consent_error(exc)

    if event.decision in {"DENIED", "REVOKED"}:
        _disable_biometrics_after_opt_out(db, employee_id)

    return consent.consent_payload(db, employee_id, include_document=False)


@router.get("/consent/document")
def download_my_biometric_consent(
    db: Session = Depends(get_db),
    principal: dict = Depends(get_current_principal),
):
    employee_id = _principal_employee_id(principal)
    event = consent.get_latest_event(db, employee_id)
    if event is None or not event.signed_pdf:
        raise HTTPException(status_code=404, detail="Aún no existe un documento firmado.")
    return Response(
        content=bytes(event.signed_pdf),
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                'attachment; filename="ASIATI_Autorizacion_Biometrica_Talent_ID.pdf"'
            )
        },
    )


@router.get("/employees/{employee_id}/consent")
def get_employee_biometric_consent(
    employee_id: str,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("talent_id.read")),
):
    try:
        return consent.consent_payload(db, employee_id, include_document=False)
    except Exception as exc:
        return _consent_error(exc)


@router.get("/employees/{employee_id}/consent/document")
def download_employee_biometric_consent(
    employee_id: str,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("talent_id.read")),
):
    event = consent.get_latest_event(db, employee_id)
    if event is None or not event.signed_pdf:
        raise HTTPException(status_code=404, detail="Aún no existe un documento firmado.")
    return Response(
        content=bytes(event.signed_pdf),
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="Talent_ID_{employee_id}_consentimiento.pdf"'
            )
        },
    )




@router.get("/employees/{employee_id}/mobile-devices")
def list_employee_mobile_devices(
    employee_id: str,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("talent_id.read")),
):
    try:
        items = [
            mobile_qr.mobile_device_payload(device)
            for device in mobile_qr.list_mobile_devices(db, employee_id)
        ]
    except Exception as exc:
        return _mobile_qr_error(exc)
    return {"items": items, "total": len(items)}


@router.delete("/employees/{employee_id}/mobile-devices/{device_id}")
def revoke_employee_mobile_device(
    employee_id: str,
    device_id: str,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("talent_id.manage")),
):
    try:
        device = mobile_qr.revoke_mobile_device(
            db,
            employee_id=employee_id,
            device_id=device_id,
        )
    except Exception as exc:
        return _mobile_qr_error(exc)
    return {
        "device": mobile_qr.mobile_device_payload(device),
        "revoked": True,
    }


@router.get("/mobile-devices")
def list_my_mobile_devices(
    db: Session = Depends(get_db),
    principal: dict = Depends(get_current_principal),
):
    employee_id = _principal_employee_id(principal)
    try:
        items = [
            mobile_qr.mobile_device_payload(device)
            for device in mobile_qr.list_mobile_devices(db, employee_id)
        ]
    except Exception as exc:
        return _mobile_qr_error(exc)
    return {"items": items, "total": len(items)}



@router.post("/mobile-devices/link-otp")
def request_my_mobile_device_link_otp(
    db: Session = Depends(get_db),
    principal: dict = Depends(get_current_principal),
):
    employee_id = _principal_employee_id(principal)
    settings = get_talent_id_qr_settings()
    try:
        return mobile_qr.request_mobile_link_otp(
            db,
            employee_id=employee_id,
            otp_secret=settings.link_otp_secret,
            ttl_seconds=settings.link_otp_ttl_seconds,
            cooldown_seconds=settings.link_otp_cooldown_seconds,
            max_attempts=settings.link_otp_max_attempts,
            send_otp=send_mobile_link_otp,
        )
    except Exception as exc:
        return _mobile_qr_error(exc)


@router.post("/mobile-devices", status_code=201)
def link_my_mobile_device(
    body: RegisterMobileDeviceRequest,
    db: Session = Depends(get_db),
    principal: dict = Depends(get_current_principal),
):
    employee_id = _principal_employee_id(principal)
    try:
        settings = get_talent_id_qr_settings()
        device = mobile_qr.register_mobile_device(
            db,
            employee_id=employee_id,
            label=body.label,
            public_key_jwk=body.public_key_jwk,
            link_challenge_id=body.link_challenge_id,
            link_otp=body.link_otp,
            link_otp_secret=settings.link_otp_secret,
        )
    except Exception as exc:
        return _mobile_qr_error(exc)
    return mobile_qr.mobile_device_payload(device)


@router.delete("/mobile-devices/{device_id}")
def revoke_my_mobile_device(
    device_id: str,
    db: Session = Depends(get_db),
    principal: dict = Depends(get_current_principal),
):
    employee_id = _principal_employee_id(principal)
    try:
        device = mobile_qr.revoke_mobile_device(
            db,
            employee_id=employee_id,
            device_id=device_id,
        )
    except Exception as exc:
        return _mobile_qr_error(exc)
    return {
        "device": mobile_qr.mobile_device_payload(device),
        "revoked": True,
    }


@router.post("/mobile-devices/{device_id}/challenge")
def create_my_mobile_qr_challenge(
    device_id: str,
    db: Session = Depends(get_db),
    principal: dict = Depends(get_current_principal),
):
    employee_id = _principal_employee_id(principal)
    settings = get_talent_id_qr_settings()
    try:
        return mobile_qr.create_signing_challenge(
            db,
            employee_id=employee_id,
            device_id=device_id,
            ttl_seconds=settings.challenge_ttl_seconds,
        )
    except Exception as exc:
        return _mobile_qr_error(exc)


@router.post("/mobile-qr")
def issue_my_mobile_qr(
    body: IssueMobileQrRequest,
    db: Session = Depends(get_db),
    principal: dict = Depends(get_current_principal),
):
    employee_id = _principal_employee_id(principal)
    settings = get_talent_id_qr_settings()
    try:
        issued = mobile_qr.issue_qr_token(
            db,
            employee_id=employee_id,
            device_id=body.device_id,
            challenge_id=body.challenge_id,
            nonce=body.nonce,
            signature_b64url=body.signature,
            token_ttl_seconds=settings.token_ttl_seconds,
            max_signature_attempts=settings.max_signature_attempts,
        )
    except Exception as exc:
        return _mobile_qr_error(exc)

    return {
        "qr_image": mobile_qr.render_qr_svg_data_url(issued["qr_payload"]),
        "expires_at": issued["expires_at"],
        "ttl_seconds": issued["ttl_seconds"],
        "device": issued["device"],
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


@router.post("/attendance/manual", status_code=201)
def create_manual_attendance(
    body: ManualAttendanceRequest,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_permission("talent_id.manage")),
):
    actor_sub = str(principal.get("sub") or "").strip()
    if not actor_sub:
        raise HTTPException(
            status_code=403,
            detail="No fue posible identificar al administrador.",
        )
    try:
        event, created = service.record_manual_attendance(
            db,
            employee_id=body.employee_id,
            event_type=body.event_type,
            reason=body.reason,
            created_by_sub=actor_sub,
            occurred_at=body.occurred_at,
        )
    except Exception as exc:
        return _translate(exc)

    return {
        **service.attendance_event_payload(event),
        "created": created,
    }


@router.get("/attendance/report")
def attendance_report(
    start_date: date = Query(...),
    end_date: date = Query(...),
    employee_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    principal: dict = Depends(get_current_principal),
):
    permissions = set(principal.get("permissions") or [])
    profile_id = str(principal.get("profile", {}).get("id") or "")

    if (
        "talent_id.attendance.read_all" in permissions
        or "talent_id.manage" in permissions
    ):
        scoped_employee_id = employee_id
    elif (
        "talent_id.attendance.read_own" in permissions
        or "profile.read_own" in permissions
    ):
        if employee_id and employee_id != profile_id:
            raise HTTPException(
                status_code=403,
                detail="Solo puedes consultar tu propia asistencia.",
            )
        scoped_employee_id = profile_id
    else:
        raise HTTPException(
            status_code=403,
            detail="No tienes permisos para consultar asistencia.",
        )

    try:
        return reporting.build_attendance_report(
            db,
            start_date=start_date,
            end_date=end_date,
            employee_id=scoped_employee_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/employees/{employee_id}/attendance")
def get_employee_attendance(
    employee_id: str,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("talent_id.read")),
):
    try:
        service.get_employee(db, employee_id)
    except Exception as exc:
        return _translate(exc)

    try:
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
    except biometrics.BiometricConsentRequired as exc:
        raise HTTPException(
            status_code=409,
            detail="El empleado debe firmar una autorización biométrica vigente antes del enrolamiento.",
        ) from exc
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


@router.get("/devices/{device_id}")
def get_device(
    device_id: str,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("talent_id.read")),
):
    try:
        device = service.get_kiosk(db, device_id)
    except Exception as exc:
        return _translate(exc)
    return service.kiosk_payload(device)


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


@router.patch("/devices/{device_id}")
def update_device(
    device_id: str,
    body: UpdateKioskRequest,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("talent_id.manage")),
):
    try:
        device = service.update_kiosk(
            db,
            device_id=device_id,
            site_id=body.site_id,
            name=body.name,
            active=body.active,
        )
    except Exception as exc:
        return _translate(exc)
    return service.kiosk_payload(device)


@router.post("/devices/{device_id}/rotate-secret")
def rotate_device_secret(
    device_id: str,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("talent_id.manage")),
):
    try:
        device, secret = service.rotate_kiosk_secret(db, device_id=device_id)
    except Exception as exc:
        return _translate(exc)

    return {
        "device": service.kiosk_payload(device),
        "device_secret": secret,
        "secret_shown_once": True,
        "rotated": True,
    }


@router.delete("/devices/{device_id}")
def delete_device(
    device_id: str,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("talent_id.manage")),
):
    try:
        device = service.revoke_kiosk(db, device_id=device_id)
    except Exception as exc:
        return _translate(exc)
    return {
        "device": service.kiosk_payload(device),
        "revoked": True,
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



@kiosk_router.post("/qr")
def consume_mobile_qr_attendance(
    body: KioskQrAttendanceRequest,
    x_device_id: str = Header(alias="X-Device-Id"),
    x_device_secret: str = Header(alias="X-Device-Secret"),
    db: Session = Depends(get_db),
):
    try:
        kiosk = service.authenticate_kiosk(
            db,
            device_id=x_device_id,
            secret=x_device_secret,
        )
    except service.InvalidKioskCredentials as exc:
        raise HTTPException(
            status_code=401,
            detail="Credenciales de dispositivo inválidas.",
        ) from exc

    try:
        employee, event, created = mobile_qr.consume_qr_attendance(
            db,
            raw_token=body.token,
            kiosk_device=kiosk,
            event_type=body.event_type,
        )
    except Exception as exc:
        return _mobile_qr_error(exc)

    return {
        "employee_id": employee.id,
        "display_name": service.employee_display_name(employee),
        "verification_method": "qr",
        "similarity": None,
        "attendance": _attendance_response(event, created=created),
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
