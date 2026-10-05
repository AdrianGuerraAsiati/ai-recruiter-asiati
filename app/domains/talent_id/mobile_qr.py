"""Linked-mobile proof of possession and dynamic QR attendance for Talent ID."""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from sqlalchemy.orm import Session
import qrcode
import qrcode.image.svg

from app.domains.talent_id.models import (
    TalentMobileDeviceLinkOtp,
    TalentMobileDevice,
    TalentMobileQrChallenge,
    TalentMobileQrToken,
)
from app.domains.talent_id.service import (
    AttendanceSiteMismatch,
    EmployeeNotEligibleForAttendance,
    TalentIdNotFound,
    employee_display_name,
    get_attendance_by_idempotency_key,
    get_employee,
    get_employee_attendance_settings,
    record_attendance,
)


QR_URI_PREFIX = "talentid://attendance?token="
QR_RECORD_RETENTION_DAYS = 2


class MobileLinkOtpCooldown(Exception):
    pass


class MobileLinkOtpInvalid(Exception):
    pass


class MobileLinkOtpExpired(Exception):
    pass


class MobileLinkOtpLocked(Exception):
    pass


class MobileLinkOtpUnavailable(Exception):
    pass


class MobileDeviceNotFound(Exception):
    pass


class MobileDeviceSignatureInvalid(Exception):
    pass


class MobileQrChallengeInvalid(Exception):
    pass


class MobileQrTokenInvalid(Exception):
    pass


class MobileQrTokenExpired(Exception):
    pass


class MobileQrTokenUsed(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _b64url_decode(value: str) -> bytes:
    normalized = str(value or "").strip()
    padding = "=" * (-len(normalized) % 4)
    return base64.urlsafe_b64decode((normalized + padding).encode("ascii"))


def _validate_public_key_jwk(jwk: dict) -> dict:
    if not isinstance(jwk, dict):
        raise ValueError("La llave pública del dispositivo no es válida.")
    if jwk.get("kty") != "EC" or jwk.get("crv") != "P-256":
        raise ValueError("Talent ID solo admite llaves ECDSA P-256.")
    x = str(jwk.get("x") or "").strip()
    y = str(jwk.get("y") or "").strip()
    if not x or not y:
        raise ValueError("La llave pública del dispositivo está incompleta.")
    try:
        x_bytes = _b64url_decode(x)
        y_bytes = _b64url_decode(y)
    except Exception as exc:
        raise ValueError("La llave pública del dispositivo no es válida.") from exc
    if len(x_bytes) != 32 or len(y_bytes) != 32:
        raise ValueError("La llave pública del dispositivo no es P-256 válida.")
    return {
        "kty": "EC",
        "crv": "P-256",
        "x": x,
        "y": y,
        "ext": True,
    }


def _public_key_from_jwk(jwk: dict):
    normalized = _validate_public_key_jwk(jwk)
    numbers = ec.EllipticCurvePublicNumbers(
        x=int.from_bytes(_b64url_decode(normalized["x"]), "big"),
        y=int.from_bytes(_b64url_decode(normalized["y"]), "big"),
        curve=ec.SECP256R1(),
    )
    return numbers.public_key()


def _canonical_message(
    *,
    employee_id: str,
    device_id: str,
    challenge_id: str,
    nonce: str,
) -> bytes:
    return (
        f"talent-id-qr:v1:{employee_id}:{device_id}:{challenge_id}:{nonce}"
    ).encode("utf-8")


def _verify_signature(
    *,
    public_key_jwk: dict,
    message: bytes,
    signature_b64url: str,
) -> None:
    try:
        raw = _b64url_decode(signature_b64url)
    except Exception as exc:
        raise MobileDeviceSignatureInvalid(
            "La firma del dispositivo no tiene un formato válido."
        ) from exc
    if len(raw) != 64:
        raise MobileDeviceSignatureInvalid(
            "La firma del dispositivo no tiene un formato válido."
        )
    r = int.from_bytes(raw[:32], "big")
    s = int.from_bytes(raw[32:], "big")
    der = encode_dss_signature(r, s)
    try:
        _public_key_from_jwk(public_key_jwk).verify(
            der,
            message,
            ec.ECDSA(hashes.SHA256()),
        )
    except (InvalidSignature, ValueError) as exc:
        raise MobileDeviceSignatureInvalid(
            "No fue posible verificar este dispositivo móvil."
        ) from exc



def _link_otp_hash(secret: str, challenge_id: str, employee_id: str, otp: str) -> str:
    payload = f"{challenge_id}:{employee_id}:{otp}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _mask_email(email: str) -> str:
    local, sep, domain = str(email or "").partition("@")
    if not sep:
        return "***"
    if len(local) <= 2:
        masked = (local[:1] or "*") + "*"
    else:
        masked = local[:2] + ("*" * max(2, len(local) - 2))
    return f"{masked}@{domain}"


def request_mobile_link_otp(
    db: Session,
    *,
    employee_id: str,
    otp_secret: str,
    ttl_seconds: int,
    cooldown_seconds: int,
    max_attempts: int,
    send_otp,
) -> dict:
    if not otp_secret.strip():
        raise MobileLinkOtpUnavailable(
            "La verificación para vincular celulares no está configurada."
        )

    employee = get_employee(db, employee_id)
    if not str(employee.email or "").strip() or "@" not in str(employee.email):
        raise MobileLinkOtpUnavailable(
            "Tu perfil no tiene un correo válido para verificar este celular. Comunícate con Talento Humano."
        )
    now = _now()
    latest = (
        db.query(TalentMobileDeviceLinkOtp)
        .filter(TalentMobileDeviceLinkOtp.employee_id == employee.id)
        .order_by(TalentMobileDeviceLinkOtp.created_at.desc())
        .first()
    )
    if (
        latest is not None
        and latest.used_at is None
        and (now - _aware(latest.created_at)).total_seconds() < cooldown_seconds
    ):
        raise MobileLinkOtpCooldown(
            "Espera antes de solicitar un nuevo código para vincular el celular."
        )

    db.query(TalentMobileDeviceLinkOtp).filter(
        TalentMobileDeviceLinkOtp.employee_id == employee.id,
        TalentMobileDeviceLinkOtp.used_at.is_(None),
    ).update({"used_at": now}, synchronize_session=False)

    challenge_id = str(uuid.uuid4())
    otp = f"{secrets.randbelow(1_000_000):06d}"
    challenge = TalentMobileDeviceLinkOtp(
        id=challenge_id,
        employee_id=employee.id,
        otp_hash=_link_otp_hash(
            otp_secret,
            challenge_id,
            employee.id,
            otp,
        ),
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


def _consume_mobile_link_otp(
    db: Session,
    *,
    employee_id: str,
    challenge_id: str,
    otp: str,
    otp_secret: str,
) -> TalentMobileDeviceLinkOtp:
    if not otp_secret.strip():
        raise MobileLinkOtpUnavailable(
            "La verificación para vincular celulares no está configurada."
        )

    challenge = (
        db.query(TalentMobileDeviceLinkOtp)
        .filter(
            TalentMobileDeviceLinkOtp.id == challenge_id,
            TalentMobileDeviceLinkOtp.employee_id == employee_id,
        )
        .with_for_update()
        .one_or_none()
    )
    if challenge is None or challenge.used_at is not None:
        raise MobileLinkOtpInvalid(
            "Solicita un nuevo código para vincular este celular."
        )

    now = _now()
    if now > _aware(challenge.expires_at):
        challenge.used_at = now
        db.commit()
        raise MobileLinkOtpExpired("El código expiró. Solicita uno nuevo.")
    if challenge.attempts >= challenge.max_attempts:
        challenge.used_at = now
        db.commit()
        raise MobileLinkOtpLocked(
            "El código fue bloqueado por demasiados intentos."
        )

    expected = _link_otp_hash(
        otp_secret,
        challenge.id,
        employee_id,
        otp.strip(),
    )
    if not hmac.compare_digest(expected, challenge.otp_hash):
        challenge.attempts += 1
        if challenge.attempts >= challenge.max_attempts:
            challenge.used_at = now
        db.commit()
        if challenge.attempts >= challenge.max_attempts:
            raise MobileLinkOtpLocked(
                "El código fue bloqueado por demasiados intentos."
            )
        raise MobileLinkOtpInvalid("El código de verificación no es válido.")

    challenge.used_at = now
    return challenge

def list_mobile_devices(db: Session, employee_id: str) -> list[TalentMobileDevice]:
    get_employee(db, employee_id)
    return (
        db.query(TalentMobileDevice)
        .filter(TalentMobileDevice.employee_id == employee_id)
        .order_by(
            TalentMobileDevice.active.desc(),
            TalentMobileDevice.created_at.desc(),
        )
        .all()
    )


def mobile_device_payload(device: TalentMobileDevice) -> dict:
    return {
        "id": device.id,
        "employee_id": device.employee_id,
        "label": device.label,
        "active": bool(device.active),
        "created_at": device.created_at.isoformat(),
        "last_used_at": (
            device.last_used_at.isoformat() if device.last_used_at else None
        ),
    }


def register_mobile_device(
    db: Session,
    *,
    employee_id: str,
    label: str,
    public_key_jwk: dict,
    link_challenge_id: str,
    link_otp: str,
    link_otp_secret: str,
) -> TalentMobileDevice:
    get_employee(db, employee_id)
    link_challenge = _consume_mobile_link_otp(
        db,
        employee_id=employee_id,
        challenge_id=link_challenge_id,
        otp=link_otp,
        otp_secret=link_otp_secret,
    )
    normalized_label = label.strip() or "Mi celular"
    if len(normalized_label) > 80:
        raise ValueError("El nombre del dispositivo es demasiado largo.")
    normalized_key = _validate_public_key_jwk(public_key_jwk)

    # One active phone per employee keeps the possession factor easy to audit.
    db.query(TalentMobileDevice).filter(
        TalentMobileDevice.employee_id == employee_id,
        TalentMobileDevice.active.is_(True),
    ).update(
        {"active": False},
        synchronize_session=False,
    )

    device = TalentMobileDevice(
        employee_id=employee_id,
        label=normalized_label,
        public_key_jwk=normalized_key,
        active=True,
    )
    db.add(device)
    link_challenge.used_at = _now()
    db.commit()
    db.refresh(device)
    return device


def revoke_mobile_device(
    db: Session,
    *,
    employee_id: str,
    device_id: str,
) -> TalentMobileDevice:
    device = (
        db.query(TalentMobileDevice)
        .filter(
            TalentMobileDevice.id == device_id,
            TalentMobileDevice.employee_id == employee_id,
        )
        .one_or_none()
    )
    if device is None:
        raise MobileDeviceNotFound("Dispositivo móvil no encontrado.")

    device.active = False
    now = _now()
    db.query(TalentMobileQrChallenge).filter(
        TalentMobileQrChallenge.mobile_device_id == device.id,
        TalentMobileQrChallenge.used_at.is_(None),
    ).update({"used_at": now}, synchronize_session=False)
    db.query(TalentMobileQrToken).filter(
        TalentMobileQrToken.mobile_device_id == device.id,
        TalentMobileQrToken.used_at.is_(None),
    ).update({"used_at": now}, synchronize_session=False)
    db.commit()
    db.refresh(device)
    return device


def _active_mobile_device(
    db: Session,
    *,
    employee_id: str,
    device_id: str,
) -> TalentMobileDevice:
    device = (
        db.query(TalentMobileDevice)
        .filter(
            TalentMobileDevice.id == device_id,
            TalentMobileDevice.employee_id == employee_id,
            TalentMobileDevice.active.is_(True),
        )
        .one_or_none()
    )
    if device is None:
        raise MobileDeviceNotFound("El celular no está vinculado o fue revocado.")
    return device


def create_signing_challenge(
    db: Session,
    *,
    employee_id: str,
    device_id: str,
    ttl_seconds: int,
) -> dict:
    _active_mobile_device(
        db,
        employee_id=employee_id,
        device_id=device_id,
    )
    now = _now()

    # QR proof rows are operational, not attendance history. Keep them bounded
    # so a phone left on the QR screen cannot grow these tables indefinitely.
    cutoff = now - timedelta(days=QR_RECORD_RETENTION_DAYS)
    db.query(TalentMobileQrChallenge).filter(
        TalentMobileQrChallenge.mobile_device_id == device_id,
        TalentMobileQrChallenge.created_at < cutoff,
    ).delete(synchronize_session=False)
    db.query(TalentMobileQrToken).filter(
        TalentMobileQrToken.mobile_device_id == device_id,
        TalentMobileQrToken.created_at < cutoff,
    ).delete(synchronize_session=False)

    # Only one usable proof challenge per linked phone.
    db.query(TalentMobileQrChallenge).filter(
        TalentMobileQrChallenge.mobile_device_id == device_id,
        TalentMobileQrChallenge.used_at.is_(None),
    ).update({"used_at": now}, synchronize_session=False)

    nonce = secrets.token_urlsafe(32)
    challenge = TalentMobileQrChallenge(
        id=str(uuid.uuid4()),
        employee_id=employee_id,
        mobile_device_id=device_id,
        nonce_hash=_sha256(nonce),
        expires_at=now + timedelta(seconds=ttl_seconds),
        attempts=0,
        created_at=now,
    )
    db.add(challenge)
    db.commit()
    db.refresh(challenge)

    return {
        "challenge_id": challenge.id,
        "nonce": nonce,
        "expires_at": challenge.expires_at.isoformat(),
        "message": (
            f"talent-id-qr:v1:{employee_id}:{device_id}:{challenge.id}:{nonce}"
        ),
    }


def issue_qr_token(
    db: Session,
    *,
    employee_id: str,
    device_id: str,
    challenge_id: str,
    nonce: str,
    signature_b64url: str,
    token_ttl_seconds: int,
    max_signature_attempts: int,
) -> dict:
    device = _active_mobile_device(
        db,
        employee_id=employee_id,
        device_id=device_id,
    )
    challenge = (
        db.query(TalentMobileQrChallenge)
        .filter(
            TalentMobileQrChallenge.id == challenge_id,
            TalentMobileQrChallenge.employee_id == employee_id,
            TalentMobileQrChallenge.mobile_device_id == device_id,
        )
        .with_for_update()
        .one_or_none()
    )
    if challenge is None or challenge.used_at is not None:
        raise MobileQrChallengeInvalid("El reto del dispositivo ya no es válido.")

    now = _now()
    if now > _aware(challenge.expires_at):
        challenge.used_at = now
        db.commit()
        raise MobileQrChallengeInvalid("El reto del dispositivo expiró.")
    if challenge.attempts >= max_signature_attempts:
        challenge.used_at = now
        db.commit()
        raise MobileQrChallengeInvalid(
            "El reto fue bloqueado por demasiados intentos."
        )
    if not secrets.compare_digest(challenge.nonce_hash, _sha256(nonce)):
        challenge.attempts += 1
        if challenge.attempts >= max_signature_attempts:
            challenge.used_at = now
        db.commit()
        raise MobileQrChallengeInvalid("El reto del dispositivo no coincide.")

    try:
        _verify_signature(
            public_key_jwk=device.public_key_jwk,
            message=_canonical_message(
                employee_id=employee_id,
                device_id=device_id,
                challenge_id=challenge.id,
                nonce=nonce,
            ),
            signature_b64url=signature_b64url,
        )
    except MobileDeviceSignatureInvalid:
        challenge.attempts += 1
        if challenge.attempts >= max_signature_attempts:
            challenge.used_at = now
        db.commit()
        raise

    challenge.used_at = now
    device.last_used_at = now

    # Replace any previously unconsumed QR for this phone. Screenshots become
    # useless as soon as the rotating credential is refreshed.
    db.query(TalentMobileQrToken).filter(
        TalentMobileQrToken.mobile_device_id == device.id,
        TalentMobileQrToken.used_at.is_(None),
    ).update({"used_at": now}, synchronize_session=False)

    raw_token = secrets.token_urlsafe(32)
    qr_token = TalentMobileQrToken(
        id=str(uuid.uuid4()),
        employee_id=employee_id,
        mobile_device_id=device.id,
        token_hash=_sha256(raw_token),
        expires_at=now + timedelta(seconds=token_ttl_seconds),
        created_at=now,
    )
    db.add(qr_token)
    db.commit()
    db.refresh(qr_token)

    return {
        "token": raw_token,
        "qr_payload": QR_URI_PREFIX + raw_token,
        "expires_at": qr_token.expires_at.isoformat(),
        "ttl_seconds": token_ttl_seconds,
        "device": mobile_device_payload(device),
    }


def render_qr_svg_data_url(payload: str) -> str:
    """Render a QR as an inline SVG data URL without exposing the token in a URL."""
    image = qrcode.make(
        payload,
        image_factory=qrcode.image.svg.SvgPathImage,
        box_size=8,
        border=3,
    )
    buffer = io.BytesIO()
    image.save(buffer)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def consume_qr_attendance(
    db: Session,
    *,
    raw_token: str,
    kiosk_device,
    event_type: str,
):
    normalized_token = str(raw_token or "").strip()
    if normalized_token.startswith(QR_URI_PREFIX):
        normalized_token = normalized_token[len(QR_URI_PREFIX):].strip()
    if not normalized_token:
        raise MobileQrTokenInvalid("El código QR no contiene una credencial válida.")

    token_hash = _sha256(normalized_token)
    token = (
        db.query(TalentMobileQrToken)
        .filter(TalentMobileQrToken.token_hash == token_hash)
        .with_for_update()
        .one_or_none()
    )
    if token is None:
        raise MobileQrTokenInvalid("El código QR no es válido.")

    idempotency_key = f"qr:{token.id}"
    existing = get_attendance_by_idempotency_key(db, idempotency_key)
    if token.used_at is not None:
        if (
            existing is not None
            and existing.device_id == kiosk_device.id
            and existing.event_type == event_type.strip().upper()
        ):
            employee = get_employee(db, existing.employee_id)
            return employee, existing, False
        raise MobileQrTokenUsed("Este código QR ya fue utilizado.")

    now = _now()
    if now > _aware(token.expires_at):
        token.used_at = now
        db.commit()
        raise MobileQrTokenExpired("El código QR expiró. Genera uno nuevo.")

    mobile_device = (
        db.query(TalentMobileDevice)
        .filter(
            TalentMobileDevice.id == token.mobile_device_id,
            TalentMobileDevice.employee_id == token.employee_id,
            TalentMobileDevice.active.is_(True),
        )
        .one_or_none()
    )
    if mobile_device is None:
        token.used_at = now
        db.commit()
        raise MobileDeviceNotFound("El celular vinculado ya no está activo.")

    settings = get_employee_attendance_settings(db, token.employee_id)
    if not settings.attendance_eligible:
        token.used_at = now
        db.commit()
        raise EmployeeNotEligibleForAttendance()
    if settings.site_id != kiosk_device.site_id:
        raise AttendanceSiteMismatch()

    event, created = record_attendance(
        db,
        employee_id=token.employee_id,
        site_id=kiosk_device.site_id,
        device_id=kiosk_device.id,
        event_type=event_type,
        method="QR",
        idempotency_key=idempotency_key,
        recognition_confidence=None,
    )

    token.used_at = now
    mobile_device.last_used_at = now
    db.commit()
    db.refresh(token)
    db.refresh(mobile_device)

    employee = get_employee(db, token.employee_id)
    return employee, event, created
