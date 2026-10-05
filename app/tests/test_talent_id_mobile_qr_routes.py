"""HTTP coverage for linked-mobile non-biometric Talent ID attendance."""

import base64
from datetime import time

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.db import Base
from app.domains.talent_id import router, service
from app.domains.talent_id.schemas import (
    IssueMobileQrRequest,
    KioskQrAttendanceRequest,
    RegisterMobileDeviceRequest,
)
from app.models import UserProfile


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _key_pair():
    private_key = ec.generate_private_key(ec.SECP256R1())
    numbers = private_key.public_key().public_numbers()
    return private_key, {
        "kty": "EC",
        "crv": "P-256",
        "x": _b64url(numbers.x.to_bytes(32, "big")),
        "y": _b64url(numbers.y.to_bytes(32, "big")),
        "ext": True,
    }


def _raw_signature(private_key, message: str) -> str:
    der = private_key.sign(
        message.encode("utf-8"),
        ec.ECDSA(hashes.SHA256()),
    )
    r, s = decode_dss_signature(der)
    return _b64url(r.to_bytes(32, "big") + s.to_bytes(32, "big"))


def test_employee_links_phone_with_otp_and_kiosk_consumes_qr(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        employee = UserProfile(
            cognito_sub="sub-mobile-route",
            email="mobile@asiati.com.co",
            login_username="mobile",
            first_name="Mobile",
            last_name="Empleado",
            status="ACTIVE",
        )
        db.add(employee)
        db.commit()
        db.refresh(employee)

        site = service.create_site(
            db,
            name="Bogotá Principal",
            code="BOG-QR",
            timezone_name="America/Bogota",
        )
        schedule = service.create_schedule(
            db,
            name="Horario QR",
            start_time=time(8, 30),
            end_time=time(18, 0),
            tolerance_minutes=10,
        )
        service.configure_employee_attendance(
            db,
            employee_id=employee.id,
            site_id=site.id,
            schedule_id=schedule.id,
            attendance_eligible=True,
        )
        kiosk, kiosk_secret = service.provision_kiosk(
            db,
            site_id=site.id,
            name="Recepción",
        )

        principal = {
            "sub": employee.cognito_sub,
            "profile": {"id": employee.id, "status": "ACTIVE"},
            "roles": ["EMPLOYEE"],
            "permissions": ["profile.read_own"],
        }
        delivered = {}
        monkeypatch.setenv("TALENT_ID_MOBILE_LINK_OTP_SECRET", "route-link-secret")
        monkeypatch.setenv("TALENT_ID_MOBILE_LINK_OTP_COOLDOWN_SECONDS", "0")
        monkeypatch.setattr(
            router,
            "send_mobile_link_otp",
            lambda email, code, ttl: delivered.update(
                email=email,
                code=code,
                ttl=ttl,
            ),
        )

        otp_response = router.request_my_mobile_device_link_otp(
            db=db,
            principal=principal,
        )
        assert otp_response["delivery"] == "EMAIL"
        assert delivered["email"] == employee.email

        private_key, jwk = _key_pair()
        linked = router.link_my_mobile_device(
            body=RegisterMobileDeviceRequest(
                label="Mi celular",
                public_key_jwk=jwk,
                link_challenge_id=otp_response["challenge_id"],
                link_otp=delivered["code"],
            ),
            db=db,
            principal=principal,
        )
        assert linked["active"] is True

        proof = router.create_my_mobile_qr_challenge(
            device_id=linked["id"],
            db=db,
            principal=principal,
        )
        issued = router.issue_my_mobile_qr(
            body=IssueMobileQrRequest(
                device_id=linked["id"],
                challenge_id=proof["challenge_id"],
                nonce=proof["nonce"],
                signature=_raw_signature(private_key, proof["message"]),
            ),
            db=db,
            principal=principal,
        )
        assert issued["qr_image"].startswith("data:image/svg+xml;base64,")

        # Service test covers raw QR content. Here issue a second token directly
        # so the HTTP kiosk route can be exercised without decoding the SVG.
        proof = router.create_my_mobile_qr_challenge(
            device_id=linked["id"],
            db=db,
            principal=principal,
        )
        from app.config import get_talent_id_qr_settings
        from app.domains.talent_id import mobile_qr

        settings = get_talent_id_qr_settings()
        raw = mobile_qr.issue_qr_token(
            db,
            employee_id=employee.id,
            device_id=linked["id"],
            challenge_id=proof["challenge_id"],
            nonce=proof["nonce"],
            signature_b64url=_raw_signature(private_key, proof["message"]),
            token_ttl_seconds=settings.token_ttl_seconds,
            max_signature_attempts=settings.max_signature_attempts,
        )

        marked = router.consume_mobile_qr_attendance(
            body=KioskQrAttendanceRequest(
                token=raw["token"],
                event_type="check_in",
            ),
            x_device_id=kiosk.id,
            x_device_secret=kiosk_secret,
            db=db,
        )

        assert marked["employee_id"] == employee.id
        assert marked["verification_method"] == "qr"
        assert marked["attendance"]["method"] == "qr"
        assert marked["attendance"]["created"] is True
    finally:
        db.close()
        engine.dispose()
