"""Kiosk facial recognition route behavior."""

import asyncio
from dataclasses import dataclass
from datetime import datetime, time, timezone
from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.datastructures import Headers

import app.models  # noqa: F401
from app.db import Base
from app.domains.talent_id import biometrics, consent, service
from app.domains.talent_id.models import TalentBiometricConsentEvent
from app.domains.talent_id.router import (
    _read_image,
    recognize_and_record_attendance,
)
from app.models import UserProfile


@dataclass(frozen=True)
class _Enrollment:
    provider_user_id: str
    face_ids: tuple[str, ...]


@dataclass(frozen=True)
class _Match:
    provider_user_id: str
    similarity: float


class FakeProvider:
    provider_name = "fake"

    def __init__(self):
        self.match = None
        self.recognize_calls = 0

    def enroll(self, *, provider_user_id: str, image_bytes: bytes):
        return _Enrollment(provider_user_id, ("face-1",))

    def recognize(self, *, image_bytes: bytes, threshold: float):
        self.recognize_calls += 1
        return self.match

    def delete_user(self, *, provider_user_id: str):
        return None


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


def _jpeg(data=b"jpeg"):
    return UploadFile(
        BytesIO(data),
        filename="face.jpg",
        headers=Headers({"content-type": "image/jpeg"}),
    )


def _setup(db):
    employee = UserProfile(
        cognito_sub="sub-kiosk",
        email="kiosk@asiati.com.co",
        first_name="Kiosco",
        last_name="Prueba",
        status="ACTIVE",
    )
    db.add(employee)
    db.commit()
    db.refresh(employee)

    site = service.create_site(
        db,
        name="Bogotá Principal",
        code="BOG-KIOSK",
        timezone_name="America/Bogota",
    )
    schedule = service.create_schedule(
        db,
        name="Horario Kiosco",
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
    db.add(
        TalentBiometricConsentEvent(
            employee_id=employee.id,
            decision="AUTHORIZED",
            document_version=consent.BIOMETRIC_CONSENT_VERSION,
            document_sha256="d" * 64,
            pdf_sha256="p" * 64,
            signed_pdf=b"%PDF-test",
            verified_email=employee.email,
            evidence={"source": "test"},
            signed_at=datetime.now(timezone.utc),
        )
    )
    db.commit()
    device, secret = service.provision_kiosk(
        db,
        site_id=site.id,
        name="Recepción Bogotá",
    )
    provider = FakeProvider()
    enrollment = biometrics.enroll_employee(
        db,
        provider=provider,
        employee_id=employee.id,
        image_bytes=b"jpeg",
    )
    provider.match = _Match(enrollment.provider_user_id, 99.7)
    return employee, device, secret, provider


def test_same_kiosk_idempotency_key_does_not_repeat_recognition(db, monkeypatch):
    monkeypatch.setenv("TALENT_ID_REKOGNITION_MATCH_THRESHOLD", "98")
    employee, device, secret, provider = _setup(db)

    first = asyncio.run(
        recognize_and_record_attendance(
            image=_jpeg(),
            event_type="check_in",
            x_device_id=device.id,
            x_device_secret=secret,
            idempotency_key="retry-key-001",
            db=db,
            provider=provider,
        )
    )
    provider.match = None
    second = asyncio.run(
        recognize_and_record_attendance(
            image=_jpeg(b"different-image"),
            event_type="check_in",
            x_device_id=device.id,
            x_device_secret=secret,
            idempotency_key="retry-key-001",
            db=db,
            provider=provider,
        )
    )

    assert first["employee_id"] == employee.id
    assert first["attendance"]["created"] is True
    assert second["employee_id"] == employee.id
    assert second["attendance"]["created"] is False
    assert second["attendance"]["id"] == first["attendance"]["id"]
    assert second["attendance"]["event_type"] == "check_in"
    assert provider.recognize_calls == 1


def test_image_reader_rejects_non_image_content_type():
    image = UploadFile(
        BytesIO(b"not-an-image"),
        filename="face.txt",
        headers=Headers({"content-type": "text/plain"}),
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(_read_image(image))

    assert exc.value.status_code == 415


def test_kiosk_explains_when_matched_employee_has_no_current_biometric_authorization(db, monkeypatch):
    monkeypatch.setenv("TALENT_ID_REKOGNITION_MATCH_THRESHOLD", "98")
    _employee, device, secret, provider = _setup(db)

    event = db.query(TalentBiometricConsentEvent).one()
    event.document_version = "stale-consent-version"
    db.commit()

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            recognize_and_record_attendance(
                image=_jpeg(),
                event_type="check_in",
                x_device_id=device.id,
                x_device_secret=secret,
                idempotency_key="consent-required-001",
                db=db,
                provider=provider,
            )
        )

    assert exc.value.status_code == 412
    detail = str(exc.value.detail)
    assert "rostro fue identificado" in detail.lower()
    assert "autorización biométrica" in detail.lower()
    assert "mi perfil" in detail.lower()
    assert "qr móvil" in detail.lower()
