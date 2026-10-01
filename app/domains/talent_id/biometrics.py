"""Provider-neutral biometric application service for Talent ID."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy.orm import Session

from app.domains.talent_id.models import (
    TalentBiometricEnrollment,
    TalentEmployeeAttendanceSetting,
)
from app.models import UserProfile


class BiometricEmployeeNotAllowed(Exception):
    pass


class BiometricProvider(Protocol):
    provider_name: str

    def enroll(self, *, provider_user_id: str, image_bytes: bytes): ...

    def recognize(self, *, image_bytes: bytes, threshold: float): ...


@dataclass(frozen=True)
class RecognizedEmployee:
    employee_id: str
    display_name: str
    similarity: float


def _allowed_employee(db: Session, employee_id: str) -> UserProfile:
    employee = (
        db.query(UserProfile)
        .filter(UserProfile.id == employee_id, UserProfile.status == "ACTIVE")
        .one_or_none()
    )
    settings = (
        db.query(TalentEmployeeAttendanceSetting)
        .filter(TalentEmployeeAttendanceSetting.employee_id == employee_id)
        .one_or_none()
    )
    if (
        employee is None
        or settings is None
        or not settings.attendance_eligible
    ):
        raise BiometricEmployeeNotAllowed()
    return employee


def _display_name(employee: UserProfile) -> str:
    full_name = " ".join(
        value.strip()
        for value in [employee.first_name or "", employee.last_name or ""]
        if value and value.strip()
    )
    return full_name or employee.email


def enroll_employee(
    db: Session,
    *,
    provider: BiometricProvider,
    employee_id: str,
    image_bytes: bytes,
) -> TalentBiometricEnrollment:
    employee = _allowed_employee(db, employee_id)
    result = provider.enroll(
        provider_user_id=employee.id,
        image_bytes=image_bytes,
    )
    face_ids = tuple(getattr(result, "face_ids", ()) or ())
    if not face_ids:
        raise ValueError("El proveedor no devolvió rostros enrolados.")

    enrollment = (
        db.query(TalentBiometricEnrollment)
        .filter(TalentBiometricEnrollment.employee_id == employee.id)
        .one_or_none()
    )
    if enrollment is None:
        enrollment = TalentBiometricEnrollment(
            employee_id=employee.id,
            provider=provider.provider_name,
            provider_user_id=str(result.provider_user_id),
            face_count=0,
            active=True,
            enrolled_at=datetime.now(timezone.utc),
        )
        db.add(enrollment)

    enrollment.provider = provider.provider_name
    enrollment.provider_user_id = str(result.provider_user_id)
    enrollment.face_count = int(enrollment.face_count or 0) + len(face_ids)
    enrollment.active = True
    db.commit()
    db.refresh(enrollment)
    return enrollment


def recognize_employee(
    db: Session,
    *,
    provider: BiometricProvider,
    image_bytes: bytes,
    match_threshold: float,
) -> RecognizedEmployee | None:
    match = provider.recognize(
        image_bytes=image_bytes,
        threshold=match_threshold,
    )
    if match is None:
        return None

    enrollment = (
        db.query(TalentBiometricEnrollment)
        .filter(
            TalentBiometricEnrollment.provider_user_id
            == str(match.provider_user_id),
            TalentBiometricEnrollment.active.is_(True),
        )
        .one_or_none()
    )
    if enrollment is None:
        return None

    try:
        employee = _allowed_employee(db, enrollment.employee_id)
    except BiometricEmployeeNotAllowed:
        return None

    return RecognizedEmployee(
        employee_id=employee.id,
        display_name=_display_name(employee),
        similarity=float(match.similarity),
    )
