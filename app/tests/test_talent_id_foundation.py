"""Talent ID foundation coverage inside Talent Intelligence."""

from datetime import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.db import Base
from app.domains.talent_id import models as talent_models  # noqa: F401
from app.domains.talent_id import service
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


def _employee(db, *, suffix="one"):
    employee = UserProfile(
        cognito_sub=f"sub-{suffix}",
        email=f"{suffix}@asiati.com.co",
        first_name="Empleado",
        last_name=suffix,
        status="ACTIVE",
    )
    db.add(employee)
    db.commit()
    db.refresh(employee)
    return employee


def test_employee_attendance_reuses_existing_user_profile(db):
    employee = _employee(db)
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

    settings = service.configure_employee_attendance(
        db,
        employee_id=employee.id,
        site_id=site.id,
        schedule_id=schedule.id,
        attendance_eligible=True,
    )

    assert settings.employee_id == employee.id
    assert db.query(UserProfile).count() == 1
    assert db.query(talent_models.TalentEmployeeAttendanceSetting).count() == 1


def test_kiosk_secret_is_returned_once_and_stored_only_as_hash(db):
    site = service.create_site(
        db,
        name="Bogotá Principal",
        code="BOG",
        timezone_name="America/Bogota",
    )

    device, secret = service.provision_kiosk(
        db,
        site_id=site.id,
        name="Recepción Bogotá",
    )

    assert secret
    assert device.token_hash != secret
    assert service.authenticate_kiosk(db, device_id=device.id, secret=secret).id == device.id

    with pytest.raises(service.InvalidKioskCredentials):
        service.authenticate_kiosk(db, device_id=device.id, secret="wrong-secret")


def test_attendance_is_idempotent_and_bound_to_employee_site(db):
    employee = _employee(db)
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
    device, _secret = service.provision_kiosk(
        db,
        site_id=site.id,
        name="Recepción Bogotá",
    )

    first, first_created = service.record_attendance(
        db,
        employee_id=employee.id,
        site_id=site.id,
        device_id=device.id,
        event_type="CHECK_IN",
        method="FACE",
        idempotency_key="idem-001",
        recognition_confidence=99.2,
    )
    second, second_created = service.record_attendance(
        db,
        employee_id=employee.id,
        site_id=site.id,
        device_id=device.id,
        event_type="CHECK_IN",
        method="FACE",
        idempotency_key="idem-001",
        recognition_confidence=99.2,
    )

    assert first.id == second.id
    assert first_created is True
    assert second_created is False
    assert db.query(talent_models.TalentAttendanceEvent).count() == 1


def test_kiosk_credentials_can_be_updated_rotated_and_revoked(db):
    bogota = service.create_site(
        db,
        name="Bogotá Principal",
        code="BOG-CRUD",
        timezone_name="America/Bogota",
    )
    medellin = service.create_site(
        db,
        name="Medellín",
        code="MDE-CRUD",
        timezone_name="America/Bogota",
    )
    device, first_secret = service.provision_kiosk(
        db,
        site_id=bogota.id,
        name="Recepción",
    )

    updated = service.update_kiosk(
        db,
        device_id=device.id,
        site_id=medellin.id,
        name="Recepción Norte",
        active=True,
    )
    assert updated.site_id == medellin.id
    assert updated.name == "Recepción Norte"

    rotated, second_secret = service.rotate_kiosk_secret(
        db,
        device_id=device.id,
    )
    assert second_secret != first_secret
    assert service.authenticate_kiosk(
        db,
        device_id=rotated.id,
        secret=second_secret,
    ).id == device.id

    with pytest.raises(service.InvalidKioskCredentials):
        service.authenticate_kiosk(
            db,
            device_id=device.id,
            secret=first_secret,
        )

    revoked = service.revoke_kiosk(db, device_id=device.id)
    assert revoked.active is False

    with pytest.raises(service.InvalidKioskCredentials):
        service.authenticate_kiosk(
            db,
            device_id=device.id,
            secret=second_secret,
        )
