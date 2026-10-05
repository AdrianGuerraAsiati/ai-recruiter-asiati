"""Manual attendance contingency coverage for Talent ID."""

from datetime import time

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.db import Base
from app.domains.talent_id import router, service
from app.domains.talent_id.schemas import ManualAttendanceRequest
from app.models import UserProfile


def test_admin_manual_attendance_is_audited():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        employee = UserProfile(
            cognito_sub="manual-employee-sub",
            email="manual.employee@asiati.com.co",
            first_name="Manual",
            last_name="Empleado",
            status="ACTIVE",
        )
        db.add(employee)
        db.commit()
        db.refresh(employee)

        site = service.create_site(
            db,
            name="Bogotá Principal",
            code="BOG-MANUAL",
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

        result = router.create_manual_attendance(
            body=ManualAttendanceRequest(
                employee_id=employee.id,
                event_type="check_in",
                reason="Falla temporal del kiosco",
            ),
            db=db,
            principal={
                "sub": "admin-audit-sub",
                "permissions": ["talent_id.manage"],
            },
        )

        assert result["employee_id"] == employee.id
        assert result["event_type"] == "CHECK_IN"
        assert result["method"] == "MANUAL"
        assert result["manual_reason"] == "Falla temporal del kiosco"
        assert result["created_by_sub"] == "admin-audit-sub"
        assert result["created"] is True
    finally:
        db.close()
        engine.dispose()
