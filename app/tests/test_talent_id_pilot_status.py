"""Pilot status coverage for Talent ID employee enrollment."""

from datetime import datetime, time, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.db import Base
from app.domains.talent_id import biometrics, router, service
from app.domains.talent_id.models import TalentBiometricConsentEvent
from app.models import UserProfile


class _Enrollment:
    provider_user_id = "employee-provider-id"
    face_ids = ("face-1",)


class _Provider:
    provider_name = "fake"

    def enroll(self, *, provider_user_id: str, image_bytes: bytes):
        assert image_bytes
        result = _Enrollment()
        result.provider_user_id = provider_user_id
        return result

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


def _employee(db):
    employee = UserProfile(
        cognito_sub="sub-pilot",
        email="pilot@asiati.com.co",
        first_name="Piloto",
        last_name="Talent ID",
        status="ACTIVE",
    )
    db.add(employee)
    db.commit()
    db.refresh(employee)
    return employee


def test_attendance_status_is_explicit_before_and_after_configuration(db):
    employee = _employee(db)

    empty = router.get_employee_attendance(
        employee_id=employee.id,
        db=db,
        _principal={},
    )
    assert empty == {
        "employee_id": employee.id,
        "configured": False,
        "site_id": None,
        "schedule_id": None,
        "attendance_eligible": False,
    }

    site = service.create_site(
        db,
        name="Bogotá Principal",
        code="BOG",
        timezone_name="America/Bogota",
    )
    schedule = service.create_schedule(
        db,
        name="Administrativo",
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

    configured = router.get_employee_attendance(
        employee_id=employee.id,
        db=db,
        _principal={},
    )
    assert configured["configured"] is True
    assert configured["site_id"] == site.id
    assert configured["schedule_id"] == schedule.id
    assert configured["attendance_eligible"] is True


def test_biometric_status_tracks_enrollment_without_raw_image_storage(db):
    employee = _employee(db)

    empty = router.get_employee_biometrics(
        employee_id=employee.id,
        db=db,
        _principal={},
    )
    assert empty["enrolled"] is False
    assert empty["face_count"] == 0
    assert empty["active"] is False

    site = service.create_site(
        db,
        name="Bogotá Principal",
        code="BOG-2",
        timezone_name="America/Bogota",
    )
    schedule = service.create_schedule(
        db,
        name="Administrativo",
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
            document_version="test",
            document_sha256="d" * 64,
            pdf_sha256="p" * 64,
            signed_pdf=b"%PDF-test",
            verified_email=employee.email,
            evidence={"source": "test"},
            signed_at=datetime.now(timezone.utc),
        )
    )
    db.commit()
    biometrics.enroll_employee(
        db,
        provider=_Provider(),
        employee_id=employee.id,
        image_bytes=b"temporary-image-only",
    )

    enrolled = router.get_employee_biometrics(
        employee_id=employee.id,
        db=db,
        _principal={},
    )
    assert enrolled["enrolled"] is True
    assert enrolled["face_count"] == 1
    assert enrolled["active"] is True
    assert enrolled["provider_cleanup_pending"] is False
    assert enrolled["provider_cleanup_last_error"] is None
    assert enrolled["provider_cleanup_attempted_at"] is None
    assert set(enrolled) == {
        "employee_id",
        "enrolled",
        "provider",
        "face_count",
        "active",
        "provider_cleanup_pending",
        "provider_cleanup_last_error",
        "provider_cleanup_attempted_at",
        "enrolled_at",
    }


def test_unknown_employee_status_is_not_treated_as_unconfigured(db):
    with pytest.raises(HTTPException) as exc_info:
        router.get_employee_attendance(
            employee_id="missing-employee",
            db=db,
            _principal={},
        )
    assert exc_info.value.status_code == 404
