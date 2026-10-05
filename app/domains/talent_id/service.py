"""Application services for the Talent ID module."""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, time, timedelta, timezone

from sqlalchemy.orm import Session

from app.domains.talent_id.models import (
    TalentAttendanceEvent,
    TalentEmployeeAttendanceSetting,
    TalentKioskDevice,
    TalentSite,
    TalentWorkSchedule,
)
from app.domains.talent_id.security import hash_device_secret, verify_device_secret
from app.models import UserProfile


class TalentIdNotFound(Exception):
    pass


class EmployeeNotEligibleForAttendance(Exception):
    pass


class InvalidKioskCredentials(Exception):
    pass


class AttendanceSiteMismatch(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _require_site(db: Session, site_id: str) -> TalentSite:
    site = (
        db.query(TalentSite)
        .filter(TalentSite.id == site_id, TalentSite.active.is_(True))
        .one_or_none()
    )
    if site is None:
        raise TalentIdNotFound("Sede no encontrada o inactiva.")
    return site


def _require_schedule(db: Session, schedule_id: str) -> TalentWorkSchedule:
    schedule = (
        db.query(TalentWorkSchedule)
        .filter(
            TalentWorkSchedule.id == schedule_id,
            TalentWorkSchedule.active.is_(True),
        )
        .one_or_none()
    )
    if schedule is None:
        raise TalentIdNotFound("Horario no encontrado o inactivo.")
    return schedule


def _require_employee(db: Session, employee_id: str) -> UserProfile:
    employee = (
        db.query(UserProfile)
        .filter(UserProfile.id == employee_id, UserProfile.status == "ACTIVE")
        .one_or_none()
    )
    if employee is None:
        raise TalentIdNotFound("Empleado no encontrado o inactivo.")
    return employee


def create_site(
    db: Session,
    *,
    name: str,
    code: str | None,
    timezone_name: str,
) -> TalentSite:
    site = TalentSite(
        name=name.strip(),
        code=code.strip().upper() if code and code.strip() else None,
        timezone=timezone_name.strip() or "America/Bogota",
        active=True,
    )
    db.add(site)
    db.commit()
    db.refresh(site)
    return site


def list_sites(db: Session) -> list[TalentSite]:
    return (
        db.query(TalentSite)
        .order_by(TalentSite.active.desc(), TalentSite.name.asc())
        .all()
    )


def get_site(db: Session, site_id: str) -> TalentSite:
    return _require_site(db, site_id)


def list_schedules(db: Session) -> list[TalentWorkSchedule]:
    return (
        db.query(TalentWorkSchedule)
        .order_by(TalentWorkSchedule.active.desc(), TalentWorkSchedule.name.asc())
        .all()
    )


def create_schedule(
    db: Session,
    *,
    name: str,
    start_time: time,
    end_time: time,
    tolerance_minutes: int,
) -> TalentWorkSchedule:
    if tolerance_minutes < 0:
        raise ValueError("tolerance_minutes must be non-negative")
    if start_time == end_time:
        raise ValueError("start_time and end_time must differ")

    schedule = TalentWorkSchedule(
        name=name.strip(),
        start_time=start_time,
        end_time=end_time,
        tolerance_minutes=tolerance_minutes,
        active=True,
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return schedule


def configure_employee_attendance(
    db: Session,
    *,
    employee_id: str,
    site_id: str,
    schedule_id: str,
    attendance_eligible: bool,
) -> TalentEmployeeAttendanceSetting:
    _require_employee(db, employee_id)
    _require_site(db, site_id)
    _require_schedule(db, schedule_id)

    settings = (
        db.query(TalentEmployeeAttendanceSetting)
        .filter(TalentEmployeeAttendanceSetting.employee_id == employee_id)
        .one_or_none()
    )
    if settings is None:
        settings = TalentEmployeeAttendanceSetting(employee_id=employee_id)
        db.add(settings)

    settings.site_id = site_id
    settings.schedule_id = schedule_id
    settings.attendance_eligible = attendance_eligible
    settings.updated_at = _now()

    db.commit()
    db.refresh(settings)
    return settings


def get_employee_attendance_settings(
    db: Session,
    employee_id: str,
) -> TalentEmployeeAttendanceSetting:
    settings = (
        db.query(TalentEmployeeAttendanceSetting)
        .filter(TalentEmployeeAttendanceSetting.employee_id == employee_id)
        .one_or_none()
    )
    if settings is None:
        raise TalentIdNotFound("Configuración de asistencia no encontrada.")
    return settings


def get_employee(db: Session, employee_id: str) -> UserProfile:
    return _require_employee(db, employee_id)


def provision_kiosk(
    db: Session,
    *,
    site_id: str,
    name: str,
) -> tuple[TalentKioskDevice, str]:
    _require_site(db, site_id)
    secret = secrets.token_urlsafe(32)
    device = TalentKioskDevice(
        site_id=site_id,
        name=name.strip(),
        token_hash=hash_device_secret(secret),
        active=True,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device, secret


def list_kiosks(db: Session) -> list[TalentKioskDevice]:
    return (
        db.query(TalentKioskDevice)
        .order_by(TalentKioskDevice.active.desc(), TalentKioskDevice.created_at.desc())
        .all()
    )


def get_kiosk(db: Session, device_id: str) -> TalentKioskDevice:
    device = (
        db.query(TalentKioskDevice)
        .filter(TalentKioskDevice.id == device_id)
        .one_or_none()
    )
    if device is None:
        raise TalentIdNotFound("Dispositivo no encontrado.")
    return device


def update_kiosk(
    db: Session,
    *,
    device_id: str,
    site_id: str | None = None,
    name: str | None = None,
    active: bool | None = None,
) -> TalentKioskDevice:
    device = get_kiosk(db, device_id)

    if site_id is not None and site_id != device.site_id:
        _require_site(db, site_id)
        device.site_id = site_id

    if name is not None:
        normalized_name = name.strip()
        if len(normalized_name) < 2:
            raise ValueError("El nombre del dispositivo es demasiado corto.")
        device.name = normalized_name

    if active is not None:
        device.active = active

    db.commit()
    db.refresh(device)
    return device


def rotate_kiosk_secret(
    db: Session,
    *,
    device_id: str,
) -> tuple[TalentKioskDevice, str]:
    device = get_kiosk(db, device_id)
    secret = secrets.token_urlsafe(32)
    device.token_hash = hash_device_secret(secret)
    db.commit()
    db.refresh(device)
    return device, secret


def revoke_kiosk(
    db: Session,
    *,
    device_id: str,
) -> TalentKioskDevice:
    device = get_kiosk(db, device_id)
    device.active = False
    # Replacing the hash invalidates the previously issued credential immediately.
    device.token_hash = hash_device_secret(secrets.token_urlsafe(48))
    db.commit()
    db.refresh(device)
    return device


def authenticate_kiosk(
    db: Session,
    *,
    device_id: str,
    secret: str,
) -> TalentKioskDevice:
    device = (
        db.query(TalentKioskDevice)
        .filter(
            TalentKioskDevice.id == device_id,
            TalentKioskDevice.active.is_(True),
        )
        .one_or_none()
    )
    if device is None or not verify_device_secret(secret, device.token_hash):
        raise InvalidKioskCredentials()

    device.last_seen_at = _now()
    db.commit()
    db.refresh(device)
    return device


def get_attendance_by_idempotency_key(
    db: Session,
    idempotency_key: str,
) -> TalentAttendanceEvent | None:
    return (
        db.query(TalentAttendanceEvent)
        .filter(TalentAttendanceEvent.idempotency_key == idempotency_key)
        .one_or_none()
    )


def employee_display_name(employee: UserProfile) -> str:
    full_name = " ".join(
        value.strip()
        for value in [employee.first_name or "", employee.last_name or ""]
        if value and value.strip()
    )
    return full_name or employee.email or "Empleado"


def record_attendance(
    db: Session,
    *,
    employee_id: str,
    site_id: str,
    device_id: str | None,
    event_type: str,
    method: str,
    idempotency_key: str,
    recognition_confidence: float | None = None,
    manual_reason: str | None = None,
    created_by_sub: str | None = None,
    occurred_at: datetime | None = None,
) -> tuple[TalentAttendanceEvent, bool]:
    existing = (
        db.query(TalentAttendanceEvent)
        .filter(TalentAttendanceEvent.idempotency_key == idempotency_key)
        .one_or_none()
    )
    if existing is not None:
        return existing, False

    employee = _require_employee(db, employee_id)
    settings = (
        db.query(TalentEmployeeAttendanceSetting)
        .filter(TalentEmployeeAttendanceSetting.employee_id == employee.id)
        .one_or_none()
    )
    if settings is None or not settings.attendance_eligible:
        raise EmployeeNotEligibleForAttendance()
    if settings.site_id != site_id:
        raise AttendanceSiteMismatch()

    _require_site(db, site_id)
    if device_id is not None:
        device = (
            db.query(TalentKioskDevice)
            .filter(
                TalentKioskDevice.id == device_id,
                TalentKioskDevice.active.is_(True),
            )
            .one_or_none()
        )
        if device is None:
            raise TalentIdNotFound("Dispositivo no encontrado o inactivo.")
        if device.site_id != site_id:
            raise AttendanceSiteMismatch()

    normalized_event = event_type.strip().upper()
    normalized_method = method.strip().upper()
    if normalized_event not in {"CHECK_IN", "CHECK_OUT"}:
        raise ValueError("unsupported attendance event type")
    if normalized_method not in {"FACE", "PIN", "QR", "MANUAL"}:
        raise ValueError("unsupported attendance method")

    normalized_reason = (manual_reason or "").strip() or None
    normalized_actor = (created_by_sub or "").strip() or None
    if normalized_method == "MANUAL":
        if normalized_reason is None or len(normalized_reason) < 5:
            raise ValueError("La marcación manual requiere un motivo de al menos 5 caracteres.")
        if normalized_actor is None:
            raise ValueError("La marcación manual requiere identificar al administrador.")
    else:
        normalized_reason = None
        normalized_actor = None

    event = TalentAttendanceEvent(
        employee_id=employee_id,
        site_id=site_id,
        device_id=device_id,
        event_type=normalized_event,
        method=normalized_method,
        idempotency_key=idempotency_key.strip(),
        recognition_confidence=recognition_confidence,
        manual_reason=normalized_reason,
        created_by_sub=normalized_actor,
        occurred_at=occurred_at or _now(),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event, True


def record_manual_attendance(
    db: Session,
    *,
    employee_id: str,
    event_type: str,
    reason: str,
    created_by_sub: str,
    occurred_at: datetime | None = None,
) -> tuple[TalentAttendanceEvent, bool]:
    """Create an audited contingency attendance event at the employee's assigned site."""
    settings = get_employee_attendance_settings(db, employee_id)
    effective_time = occurred_at or _now()
    if effective_time.tzinfo is None:
        effective_time = effective_time.replace(tzinfo=timezone.utc)
    else:
        effective_time = effective_time.astimezone(timezone.utc)

    now = _now()
    if effective_time > now.replace(microsecond=0) + timedelta(minutes=5):
        raise ValueError("La hora de contingencia no puede estar en el futuro.")
    if effective_time < now - timedelta(days=31):
        raise ValueError("La marcación manual solo puede registrarse hasta 31 días atrás.")

    if not settings.attendance_eligible:
        raise EmployeeNotEligibleForAttendance()
    if not settings.site_id:
        raise TalentIdNotFound("El empleado no tiene una sede asignada.")

    return record_attendance(
        db,
        employee_id=employee_id,
        site_id=settings.site_id,
        device_id=None,
        event_type=event_type,
        method="MANUAL",
        idempotency_key=f"manual:{uuid.uuid4()}",
        recognition_confidence=None,
        manual_reason=reason,
        created_by_sub=created_by_sub,
        occurred_at=effective_time,
    )


def site_payload(site: TalentSite) -> dict:
    return {
        "id": site.id,
        "name": site.name,
        "code": site.code,
        "timezone": site.timezone,
        "active": bool(site.active),
    }


def schedule_payload(schedule: TalentWorkSchedule) -> dict:
    return {
        "id": schedule.id,
        "name": schedule.name,
        "start_time": schedule.start_time.isoformat(),
        "end_time": schedule.end_time.isoformat(),
        "tolerance_minutes": schedule.tolerance_minutes,
        "active": bool(schedule.active),
    }


def kiosk_payload(device: TalentKioskDevice) -> dict:
    return {
        "id": device.id,
        "site_id": device.site_id,
        "name": device.name,
        "active": bool(device.active),
        "secret_retrievable": False,
        "created_at": device.created_at.isoformat(),
        "last_seen_at": (
            device.last_seen_at.isoformat() if device.last_seen_at else None
        ),
    }


def attendance_event_payload(event: TalentAttendanceEvent) -> dict:
    return {
        "id": event.id,
        "employee_id": event.employee_id,
        "site_id": event.site_id,
        "device_id": event.device_id,
        "event_type": event.event_type,
        "method": event.method,
        "occurred_at": event.occurred_at.isoformat(),
        "recognition_confidence": event.recognition_confidence,
        "manual_reason": event.manual_reason,
        "created_by_sub": event.created_by_sub,
    }
