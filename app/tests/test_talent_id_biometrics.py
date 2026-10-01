"""Biometric Talent ID service coverage."""

from dataclasses import dataclass

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.db import Base
from app.domains.talent_id import biometrics, service
from app.domains.talent_id.models import TalentBiometricEnrollment
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
        self.enroll_calls = 0
        self.recognize_calls = 0
        self.match = None

    def enroll(self, *, provider_user_id: str, image_bytes: bytes):
        self.enroll_calls += 1
        assert image_bytes
        return _Enrollment(provider_user_id=provider_user_id, face_ids=("face-1",))

    def recognize(self, *, image_bytes: bytes, threshold: float):
        self.recognize_calls += 1
        assert image_bytes
        assert threshold > 0
        return self.match


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


def _employee(db, *, suffix="one"):
    employee = UserProfile(
        cognito_sub=f"sub-{suffix}",
        email=f"{suffix}@asiati.com.co",
        first_name="Ana",
        last_name="Prueba",
        status="ACTIVE",
    )
    db.add(employee)
    db.commit()
    db.refresh(employee)

    site = service.create_site(
        db,
        name="Bogotá Principal",
        code=f"BOG-{suffix}",
        timezone_name="America/Bogota",
    )
    schedule = service.create_schedule(
        db,
        name=f"Horario {suffix}",
        start_time=__import__("datetime").time(8, 30),
        end_time=__import__("datetime").time(18, 0),
        tolerance_minutes=10,
    )
    service.configure_employee_attendance(
        db,
        employee_id=employee.id,
        site_id=site.id,
        schedule_id=schedule.id,
        attendance_eligible=True,
    )
    return employee


def test_enrollment_reuses_canonical_employee_and_upserts_face_count(db):
    employee = _employee(db)
    provider = FakeProvider()

    first = biometrics.enroll_employee(
        db,
        provider=provider,
        employee_id=employee.id,
        image_bytes=b"jpeg-one",
    )
    second = biometrics.enroll_employee(
        db,
        provider=provider,
        employee_id=employee.id,
        image_bytes=b"jpeg-two",
    )

    assert first.employee_id == employee.id
    assert second.employee_id == employee.id
    assert second.face_count == 2
    assert provider.enroll_calls == 2
    assert db.query(UserProfile).count() == 1
    assert db.query(TalentBiometricEnrollment).count() == 1


def test_recognition_resolves_active_attendance_eligible_employee(db):
    employee = _employee(db)
    provider = FakeProvider()
    enrollment = biometrics.enroll_employee(
        db,
        provider=provider,
        employee_id=employee.id,
        image_bytes=b"jpeg",
    )
    provider.match = _Match(
        provider_user_id=enrollment.provider_user_id,
        similarity=99.4,
    )

    recognized = biometrics.recognize_employee(
        db,
        provider=provider,
        image_bytes=b"jpeg",
        match_threshold=98.0,
    )

    assert recognized is not None
    assert recognized.employee_id == employee.id
    assert recognized.display_name == "Ana Prueba"
    assert recognized.similarity == 99.4


def test_recognition_rejects_employee_disabled_for_attendance(db):
    employee = _employee(db)
    provider = FakeProvider()
    enrollment = biometrics.enroll_employee(
        db,
        provider=provider,
        employee_id=employee.id,
        image_bytes=b"jpeg",
    )
    settings = service.get_employee_attendance_settings(db, employee.id)
    settings.attendance_eligible = False
    db.commit()

    provider.match = _Match(
        provider_user_id=enrollment.provider_user_id,
        similarity=99.8,
    )

    assert biometrics.recognize_employee(
        db,
        provider=provider,
        image_bytes=b"jpeg",
        match_threshold=98.0,
    ) is None


def test_provider_user_id_is_stable_employee_identity(db):
    employee = _employee(db)
    provider = FakeProvider()

    enrollment = biometrics.enroll_employee(
        db,
        provider=provider,
        employee_id=employee.id,
        image_bytes=b"jpeg",
    )

    assert enrollment.provider_user_id == employee.id
