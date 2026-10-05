"""Linked-mobile dynamic QR attendance coverage."""

import base64
from datetime import time

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.db import Base
from app.domains.talent_id import mobile_qr, service
from app.models import UserProfile


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _key_pair():
    private_key = ec.generate_private_key(ec.SECP256R1())
    numbers = private_key.public_key().public_numbers()
    jwk = {
        "kty": "EC",
        "crv": "P-256",
        "x": _b64url(numbers.x.to_bytes(32, "big")),
        "y": _b64url(numbers.y.to_bytes(32, "big")),
        "ext": True,
    }
    return private_key, jwk


def _raw_signature(private_key, message: str) -> str:
    der = private_key.sign(
        message.encode("utf-8"),
        ec.ECDSA(hashes.SHA256()),
    )
    r, s = decode_dss_signature(der)
    return _b64url(r.to_bytes(32, "big") + s.to_bytes(32, "big"))


def _employee(db, suffix="one"):
    employee = UserProfile(
        cognito_sub=f"sub-qr-{suffix}",
        email=f"qr-{suffix}@asiati.com.co",
        first_name="QR",
        last_name="Empleado",
        status="ACTIVE",
    )
    db.add(employee)
    db.commit()
    db.refresh(employee)
    return employee


def _attendance_ready(db, employee, suffix="one"):
    site = service.create_site(
        db,
        name=f"Sede {suffix}",
        code=f"QR-{suffix}",
        timezone_name="America/Bogota",
    )
    schedule = service.create_schedule(
        db,
        name=f"Horario {suffix}",
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
    kiosk, secret = service.provision_kiosk(
        db,
        site_id=site.id,
        name=f"Kiosco {suffix}",
    )
    return site, kiosk, secret


def test_linked_phone_signs_challenge_and_issues_short_lived_qr(db):
    employee = _employee(db)
    private_key, jwk = _key_pair()
    device = mobile_qr.register_mobile_device(
        db,
        employee_id=employee.id,
        label="Pixel de prueba",
        public_key_jwk=jwk,
    )

    challenge = mobile_qr.create_signing_challenge(
        db,
        employee_id=employee.id,
        device_id=device.id,
        ttl_seconds=60,
    )
    signature = _raw_signature(private_key, challenge["message"])

    issued = mobile_qr.issue_qr_token(
        db,
        employee_id=employee.id,
        device_id=device.id,
        challenge_id=challenge["challenge_id"],
        nonce=challenge["nonce"],
        signature_b64url=signature,
        token_ttl_seconds=30,
        max_signature_attempts=5,
    )

    assert issued["qr_payload"].startswith(mobile_qr.QR_URI_PREFIX)
    assert issued["ttl_seconds"] == 30
    assert issued["device"]["id"] == device.id
    assert mobile_qr.render_qr_svg_data_url(issued["qr_payload"]).startswith(
        "data:image/svg+xml;base64,"
    )


def test_wrong_private_key_cannot_issue_qr(db):
    employee = _employee(db)
    _private_key, jwk = _key_pair()
    attacker_key, _ = _key_pair()
    device = mobile_qr.register_mobile_device(
        db,
        employee_id=employee.id,
        label="Celular",
        public_key_jwk=jwk,
    )
    challenge = mobile_qr.create_signing_challenge(
        db,
        employee_id=employee.id,
        device_id=device.id,
        ttl_seconds=60,
    )

    with pytest.raises(mobile_qr.MobileDeviceSignatureInvalid):
        mobile_qr.issue_qr_token(
            db,
            employee_id=employee.id,
            device_id=device.id,
            challenge_id=challenge["challenge_id"],
            nonce=challenge["nonce"],
            signature_b64url=_raw_signature(attacker_key, challenge["message"]),
            token_ttl_seconds=30,
            max_signature_attempts=5,
        )


def test_kiosk_consumes_qr_once_and_records_qr_method(db):
    employee = _employee(db)
    _site, kiosk, _secret = _attendance_ready(db, employee)
    private_key, jwk = _key_pair()
    device = mobile_qr.register_mobile_device(
        db,
        employee_id=employee.id,
        label="Celular",
        public_key_jwk=jwk,
    )
    challenge = mobile_qr.create_signing_challenge(
        db,
        employee_id=employee.id,
        device_id=device.id,
        ttl_seconds=60,
    )
    issued = mobile_qr.issue_qr_token(
        db,
        employee_id=employee.id,
        device_id=device.id,
        challenge_id=challenge["challenge_id"],
        nonce=challenge["nonce"],
        signature_b64url=_raw_signature(private_key, challenge["message"]),
        token_ttl_seconds=30,
        max_signature_attempts=5,
    )

    first_employee, first_event, first_created = mobile_qr.consume_qr_attendance(
        db,
        raw_token=issued["qr_payload"],
        kiosk_device=kiosk,
        event_type="check_in",
    )
    second_employee, second_event, second_created = mobile_qr.consume_qr_attendance(
        db,
        raw_token=issued["qr_payload"],
        kiosk_device=kiosk,
        event_type="check_in",
    )

    assert first_employee.id == employee.id
    assert second_employee.id == employee.id
    assert first_event.id == second_event.id
    assert first_event.method == "QR"
    assert first_created is True
    assert second_created is False

    with pytest.raises(mobile_qr.MobileQrTokenUsed):
        mobile_qr.consume_qr_attendance(
            db,
            raw_token=issued["qr_payload"],
            kiosk_device=kiosk,
            event_type="check_out",
        )


def test_linking_new_phone_revokes_previous_phone(db):
    employee = _employee(db)
    _, first_jwk = _key_pair()
    _, second_jwk = _key_pair()

    first = mobile_qr.register_mobile_device(
        db,
        employee_id=employee.id,
        label="Celular anterior",
        public_key_jwk=first_jwk,
    )
    second = mobile_qr.register_mobile_device(
        db,
        employee_id=employee.id,
        label="Celular nuevo",
        public_key_jwk=second_jwk,
    )
    db.refresh(first)

    assert first.active is False
    assert second.active is True

    with pytest.raises(mobile_qr.MobileDeviceNotFound):
        mobile_qr.create_signing_challenge(
            db,
            employee_id=employee.id,
            device_id=first.id,
            ttl_seconds=60,
        )
