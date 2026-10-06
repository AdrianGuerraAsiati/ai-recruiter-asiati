"""Provider-neutral biometric application service for Talent ID."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy.orm import Session

from app.domains.talent_id import consent
from app.domains.talent_id.models import (
    TalentBiometricEnrollment,
    TalentEmployeeAttendanceSetting,
)
from app.models import UserProfile


class BiometricEmployeeNotAllowed(Exception):
    pass


class BiometricConsentRequired(Exception):
    pass


class BiometricProvider(Protocol):
    provider_name: str

    def enroll(self, *, provider_user_id: str, image_bytes: bytes): ...

    def recognize(self, *, image_bytes: bytes, threshold: float): ...

    def delete_user(self, *, provider_user_id: str): ...


@dataclass(frozen=True)
class RecognizedEmployee:
    employee_id: str
    display_name: str
    similarity: float


@dataclass(frozen=True)
class BiometricDiagnostic:
    selected_employee_id: str
    matched_employee_id: str | None
    matched_display_name: str | None
    similarity: float | None
    required_similarity: float
    passes_threshold: bool
    matches_selected_employee: bool


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
    if consent.current_status(db, employee_id) != "AUTHORIZED":
        raise BiometricConsentRequired()
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
    enrollment.provider_cleanup_pending = False
    enrollment.provider_cleanup_last_error = None
    enrollment.provider_cleanup_attempted_at = None
    db.commit()
    db.refresh(enrollment)
    return enrollment



def get_employee_enrollment(
    db: Session,
    employee_id: str,
) -> TalentBiometricEnrollment | None:
    """Return the current biometric enrollment record, if any."""
    return (
        db.query(TalentBiometricEnrollment)
        .filter(TalentBiometricEnrollment.employee_id == employee_id)
        .one_or_none()
    )

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

    if consent.current_status(db, enrollment.employee_id) != "AUTHORIZED":
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



def diagnose_employee(
    db: Session,
    *,
    provider: BiometricProvider,
    employee_id: str,
    image_bytes: bytes,
    match_threshold: float,
    diagnostic_floor: float = 50.0,
) -> BiometricDiagnostic:
    """Probe recognition for an administrator without recording attendance."""
    selected = _allowed_employee(db, employee_id)
    if consent.current_status(db, selected.id) != "AUTHORIZED":
        raise BiometricConsentRequired()

    enrollment = get_employee_enrollment(db, selected.id)
    if enrollment is None or not enrollment.active:
        raise ValueError("El empleado no tiene un enrolamiento biométrico activo.")

    floor = min(float(match_threshold), max(0.0, float(diagnostic_floor)))
    match = provider.recognize(
        image_bytes=image_bytes,
        threshold=floor,
    )
    if match is None:
        return BiometricDiagnostic(
            selected_employee_id=selected.id,
            matched_employee_id=None,
            matched_display_name=None,
            similarity=None,
            required_similarity=float(match_threshold),
            passes_threshold=False,
            matches_selected_employee=False,
        )

    matched_enrollment = (
        db.query(TalentBiometricEnrollment)
        .filter(
            TalentBiometricEnrollment.provider_user_id == str(match.provider_user_id),
            TalentBiometricEnrollment.active.is_(True),
        )
        .one_or_none()
    )
    if matched_enrollment is None:
        return BiometricDiagnostic(
            selected_employee_id=selected.id,
            matched_employee_id=None,
            matched_display_name=None,
            similarity=float(match.similarity),
            required_similarity=float(match_threshold),
            passes_threshold=False,
            matches_selected_employee=False,
        )

    matched_employee = (
        db.query(UserProfile)
        .filter(UserProfile.id == matched_enrollment.employee_id)
        .one_or_none()
    )
    matches_selected = matched_enrollment.employee_id == selected.id
    similarity = float(match.similarity)

    return BiometricDiagnostic(
        selected_employee_id=selected.id,
        matched_employee_id=matched_enrollment.employee_id,
        matched_display_name=(
            _display_name(matched_employee) if matched_employee is not None else None
        ),
        similarity=similarity,
        required_similarity=float(match_threshold),
        passes_threshold=bool(matches_selected and similarity >= float(match_threshold)),
        matches_selected_employee=matches_selected,
    )


def _attempt_provider_cleanup(
    db: Session,
    *,
    enrollment: TalentBiometricEnrollment,
    provider: BiometricProvider,
) -> None:
    enrollment.provider_cleanup_pending = True
    enrollment.provider_cleanup_attempted_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(enrollment)

    try:
        provider.delete_user(provider_user_id=enrollment.provider_user_id)
    except Exception as exc:
        enrollment.provider_cleanup_pending = True
        enrollment.provider_cleanup_last_error = str(exc)[:1000] or exc.__class__.__name__
        enrollment.provider_cleanup_attempted_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(enrollment)
        raise

    enrollment.provider_cleanup_pending = False
    enrollment.provider_cleanup_last_error = None
    enrollment.provider_cleanup_attempted_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(enrollment)


def revoke_employee_enrollment(
    db: Session,
    *,
    employee_id: str,
    provider: BiometricProvider | None = None,
) -> bool:
    """Disable recognition immediately and track provider deletion until confirmed."""
    enrollment = get_employee_enrollment(db, employee_id)
    if enrollment is None:
        return False

    enrollment.active = False
    enrollment.face_count = 0
    enrollment.provider_cleanup_pending = True
    enrollment.provider_cleanup_last_error = None
    db.commit()
    db.refresh(enrollment)

    if provider is not None:
        _attempt_provider_cleanup(
            db,
            enrollment=enrollment,
            provider=provider,
        )
    return True


def retry_provider_cleanup(
    db: Session,
    *,
    employee_id: str,
    provider: BiometricProvider,
) -> TalentBiometricEnrollment:
    enrollment = get_employee_enrollment(db, employee_id)
    if enrollment is None:
        raise ValueError("El empleado no tiene enrolamiento biométrico.")

    _attempt_provider_cleanup(
        db,
        enrollment=enrollment,
        provider=provider,
    )
    return enrollment
