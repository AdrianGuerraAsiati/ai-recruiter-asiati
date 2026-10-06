"""Manual attendance contingency coverage for Talent ID."""

from datetime import datetime, time, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.db import Base
from app.domains.talent_id import router, service
from app.domains.talent_id.schemas import ManualAttendanceRequest
from app.models import UserProfile


def test_admin_manual_attendance_route_is_suspended_for_report_only_ingestion():
    with pytest.raises(Exception) as exc:
        router.create_manual_attendance(
            body=ManualAttendanceRequest(
                employee_id="employee-1",
                event_type="check_in",
                reason="Falla temporal del equipo",
            ),
            db=None,
            principal={
                "sub": "admin-audit-sub",
                "permissions": ["talent_id.manage"],
            },
        )

    assert getattr(exc.value, "status_code", None) == 410
    assert "reportes" in str(getattr(exc.value, "detail", "")).lower()



def test_manual_attendance_rejects_future_time():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        employee = UserProfile(
            cognito_sub="manual-future-sub",
            email="manual.future@asiati.com.co",
            first_name="Future",
            last_name="Empleado",
            status="ACTIVE",
        )
        db.add(employee)
        db.commit()
        db.refresh(employee)

        site = service.create_site(
            db,
            name="Bogotá",
            code="BOG-FUTURE",
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

        with pytest.raises(ValueError, match="futuro"):
            service.record_manual_attendance(
                db,
                employee_id=employee.id,
                event_type="check_in",
                reason="Prueba de hora inválida",
                created_by_sub="admin-sub",
                occurred_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )
    finally:
        db.close()
        engine.dispose()
