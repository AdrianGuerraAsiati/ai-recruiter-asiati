"""Digital biometric consent and electronic-signature support for Talent ID."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import textwrap
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable

import fitz
from sqlalchemy.orm import Session

from app.domains.talent_id.models import (
    TalentBiometricConsentEvent,
    TalentBiometricConsentOtp,
)
from app.models import UserProfile


BIOMETRIC_CONSENT_VERSION = "1.0"
BIOMETRIC_CONSENT_TITLE = (
    "Autorización para el tratamiento de datos biométricos - Talent ID"
)
BIOMETRIC_CONSENT_TEXT = """Declaro que ASIATI me informó de forma previa, clara y suficiente que las fotografías de mi rostro y las características o representaciones biométricas derivadas de ellas constituyen datos personales sensibles.

Autorizo, cuando mi decisión sea AUTORIZAR, que ASIATI trate estos datos exclusivamente para enrolar mi identidad en Talent ID, verificar mi identidad mediante reconocimiento facial, registrar entradas y salidas en los sistemas corporativos de asistencia y prevenir suplantaciones o marcaciones por terceros.

Entiendo que la autorización biométrica es voluntaria. Si no autorizo el tratamiento, o si posteriormente revoco una autorización vigente, ASIATI debe mantener disponible un mecanismo alternativo de marcación que no implique el tratamiento de datos biométricos.

ASIATI aplicará medidas técnicas, administrativas y humanas para proteger esta información. Talent ID no conserva como archivo permanente la fotografía original utilizada para enrolamiento; mantiene los identificadores técnicos necesarios para operar el proveedor biométrico mientras exista una autorización vigente y una finalidad legítima.

He sido informado de que puedo conocer, actualizar y rectificar mis datos, solicitar información sobre su uso, presentar consultas o reclamos, solicitar la supresión cuando proceda y revocar esta autorización en los casos permitidos por la legislación aplicable.

Esta decisión se firma electrónicamente mediante mi cuenta autenticada de Talent y un código OTP de un solo uso enviado a mi correo registrado. La evidencia de firma conserva la versión exacta del documento, fecha y hora, decisión, identificadores de verificación y huellas criptográficas de integridad."""


class ConsentOtpCooldown(Exception):
    pass


class ConsentOtpUnavailable(Exception):
    pass


class ConsentOtpInvalid(Exception):
    pass


class ConsentOtpExpired(Exception):
    pass


class ConsentOtpLocked(Exception):
    pass


class ConsentStateError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _employee(db: Session, employee_id: str) -> UserProfile:
    employee = (
        db.query(UserProfile)
        .filter(UserProfile.id == employee_id, UserProfile.status == "ACTIVE")
        .one_or_none()
    )
    if employee is None:
        raise ValueError("Empleado no encontrado o inactivo.")
    return employee


def _otp_hash(secret: str, challenge_id: str, otp: str) -> str:
    payload = f"{challenge_id}:{otp}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _mask_email(email: str) -> str:
    local, sep, domain = email.partition("@")
    if not sep:
        return "***"
    if len(local) <= 2:
        masked = local[:1] + "*"
    else:
        masked = local[:2] + ("*" * max(2, len(local) - 2))
    return f"{masked}@{domain}"


def document_sha256() -> str:
    payload = f"{BIOMETRIC_CONSENT_VERSION}\n{BIOMETRIC_CONSENT_TEXT}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def hash_evidence_value(secret: str, value: str | None) -> str | None:
    normalized = (value or "").strip()
    if not normalized:
        return None
    return hmac.new(
        secret.encode("utf-8"),
        normalized.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def get_latest_event(
    db: Session,
    employee_id: str,
) -> TalentBiometricConsentEvent | None:
    return (
        db.query(TalentBiometricConsentEvent)
        .filter(TalentBiometricConsentEvent.employee_id == employee_id)
        .order_by(TalentBiometricConsentEvent.signed_at.desc())
        .first()
    )


def current_status(db: Session, employee_id: str) -> str:
    event = get_latest_event(db, employee_id)
    return event.decision if event is not None else "PENDING"


def consent_payload(
    db: Session,
    employee_id: str,
    *,
    include_document: bool = True,
) -> dict:
    employee = _employee(db, employee_id)
    event = get_latest_event(db, employee.id)
    payload = {
        "employee_id": employee.id,
        "status": event.decision if event else "PENDING",
        "signed_at": event.signed_at.isoformat() if event else None,
        "document_version": (
            event.document_version if event else BIOMETRIC_CONSENT_VERSION
        ),
        "document_sha256": (
            event.document_sha256 if event else document_sha256()
        ),
        "pdf_sha256": event.pdf_sha256 if event else None,
        "verified_email": (
            _mask_email(event.verified_email) if event else _mask_email(employee.email)
        ),
        "has_signed_document": bool(event and event.signed_pdf),
    }
    if include_document:
        payload["document"] = {
            "title": BIOMETRIC_CONSENT_TITLE,
            "version": BIOMETRIC_CONSENT_VERSION,
            "text": BIOMETRIC_CONSENT_TEXT,
        }
    return payload


def request_otp(
    db: Session,
    *,
    employee_id: str,
    otp_secret: str,
    ttl_seconds: int,
    cooldown_seconds: int,
    max_attempts: int,
    send_otp: Callable[[str, str, int], None],
) -> dict:
    if not otp_secret.strip():
        raise ConsentOtpUnavailable("La firma electrónica no está configurada.")

    employee = _employee(db, employee_id)
    now = _now()

    latest = (
        db.query(TalentBiometricConsentOtp)
        .filter(TalentBiometricConsentOtp.employee_id == employee.id)
        .order_by(TalentBiometricConsentOtp.created_at.desc())
        .first()
    )
    if (
        latest is not None
        and latest.used_at is None
        and (now - _aware(latest.created_at)).total_seconds() < cooldown_seconds
    ):
        raise ConsentOtpCooldown("Espera antes de solicitar un nuevo código.")

    challenge_id = str(uuid.uuid4())
    otp = f"{secrets.randbelow(1_000_000):06d}"
    challenge = TalentBiometricConsentOtp(
        id=challenge_id,
        employee_id=employee.id,
        otp_hash=_otp_hash(otp_secret, challenge_id, otp),
        expires_at=now + timedelta(seconds=ttl_seconds),
        attempts=0,
        max_attempts=max_attempts,
        created_at=now,
    )
    db.add(challenge)
    db.flush()

    try:
        send_otp(employee.email, otp, ttl_seconds)
    except Exception:
        db.rollback()
        raise

    db.commit()
    return {
        "challenge_id": challenge.id,
        "delivery": "EMAIL",
        "destination": _mask_email(employee.email),
        "expires_in_seconds": ttl_seconds,
    }


def _latest_open_challenge(
    db: Session,
    employee_id: str,
) -> TalentBiometricConsentOtp:
    challenge = (
        db.query(TalentBiometricConsentOtp)
        .filter(
            TalentBiometricConsentOtp.employee_id == employee_id,
            TalentBiometricConsentOtp.used_at.is_(None),
        )
        .order_by(TalentBiometricConsentOtp.created_at.desc())
        .first()
    )
    if challenge is None:
        raise ConsentOtpInvalid("Solicita un nuevo código de verificación.")
    return challenge


def _validate_transition(current: str, decision: str) -> None:
    if decision not in {"AUTHORIZED", "DENIED", "REVOKED"}:
        raise ConsentStateError("Decisión de consentimiento inválida.")
    if decision == "REVOKED" and current != "AUTHORIZED":
        raise ConsentStateError("Solo una autorización vigente puede revocarse.")
    if current == "AUTHORIZED" and decision == "DENIED":
        raise ConsentStateError(
            "Para retirar una autorización vigente utiliza la opción de revocar."
        )


def _display_name(employee: UserProfile) -> str:
    full_name = " ".join(
        part.strip()
        for part in [employee.first_name or "", employee.last_name or ""]
        if part and part.strip()
    )
    return full_name or employee.email


def _render_signed_pdf(
    *,
    employee: UserProfile,
    decision: str,
    signed_at: datetime,
    event_id: str,
) -> bytes:
    local_time = signed_at.astimezone(
        __import__("zoneinfo").ZoneInfo("America/Bogota")
    )
    decision_label = {
        "AUTHORIZED": "AUTORIZO",
        "DENIED": "NO AUTORIZO",
        "REVOKED": "REVOCO AUTORIZACIÓN PREVIA",
    }[decision]

    lines = [
        "ASIATI - TALENT INTELLIGENCE",
        BIOMETRIC_CONSENT_TITLE,
        f"Versión {BIOMETRIC_CONSENT_VERSION}",
        "",
        f"Empleado: {_display_name(employee)}",
        f"Usuario Talent: {employee.login_username or 'No registrado'}",
        f"Correo verificado: {employee.email}",
        f"ID interno: {employee.id}",
        "",
        *textwrap.wrap(BIOMETRIC_CONSENT_TEXT, width=95),
        "",
        f"DECISIÓN DEL TITULAR: {decision_label}",
        f"Fecha y hora: {local_time.strftime('%Y-%m-%d %H:%M:%S %Z')}",
        f"ID de evidencia: {event_id}",
        "",
        "Firma electrónica: cuenta Talent autenticada + código OTP de un solo uso.",
        "La huella SHA-256 del PDF se conserva en Talent Intelligence para verificar integridad.",
    ]

    doc = fitz.open()
    page = None
    y = 55
    for idx, line in enumerate(lines):
        if page is None or y > 790:
            page = doc.new_page(width=595, height=842)
            y = 55
        font_size = 13 if idx in {0, 1} else 9.5
        if idx == 0:
            font_size = 14
        page.insert_text(
            (50, y),
            line,
            fontsize=font_size,
            fontname="helv",
        )
        y += 18 if font_size >= 13 else 13
    return doc.tobytes(garbage=4, deflate=True)


def sign_decision(
    db: Session,
    *,
    employee_id: str,
    decision: str,
    otp: str,
    expected_document_version: str,
    otp_secret: str,
    evidence: dict | None = None,
) -> TalentBiometricConsentEvent:
    if expected_document_version != BIOMETRIC_CONSENT_VERSION:
        raise ConsentStateError(
            "La autorización cambió. Actualiza la pantalla antes de firmar."
        )
    if not otp_secret.strip():
        raise ConsentOtpUnavailable("La firma electrónica no está configurada.")

    employee = _employee(db, employee_id)
    current = current_status(db, employee.id)
    normalized_decision = decision.strip().upper()
    _validate_transition(current, normalized_decision)

    challenge = _latest_open_challenge(db, employee.id)
    now = _now()
    if now > _aware(challenge.expires_at):
        raise ConsentOtpExpired("El código expiró. Solicita uno nuevo.")
    if challenge.attempts >= challenge.max_attempts:
        raise ConsentOtpLocked("El código fue bloqueado por demasiados intentos.")

    expected = _otp_hash(otp_secret, challenge.id, otp.strip())
    if not hmac.compare_digest(expected, challenge.otp_hash):
        challenge.attempts += 1
        db.commit()
        if challenge.attempts >= challenge.max_attempts:
            raise ConsentOtpLocked("El código fue bloqueado por demasiados intentos.")
        raise ConsentOtpInvalid("El código de verificación no es válido.")

    event_id = str(uuid.uuid4())
    pdf_bytes = _render_signed_pdf(
        employee=employee,
        decision=normalized_decision,
        signed_at=now,
        event_id=event_id,
    )
    event = TalentBiometricConsentEvent(
        id=event_id,
        employee_id=employee.id,
        decision=normalized_decision,
        document_version=BIOMETRIC_CONSENT_VERSION,
        document_sha256=document_sha256(),
        pdf_sha256=hashlib.sha256(pdf_bytes).hexdigest(),
        signed_pdf=pdf_bytes,
        verified_email=employee.email,
        otp_challenge_id=challenge.id,
        evidence=evidence or {},
        signed_at=now,
    )
    challenge.used_at = now
    db.add(event)
    db.commit()
    db.refresh(event)
    return event
