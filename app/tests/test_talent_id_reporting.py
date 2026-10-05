"""Attendance report coverage for Talent ID."""

from datetime import date, datetime, time, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.db import Base
from app.domains.talent_id import reporting, service
from app.domains.talent_id.models import TalentAttendanceEvent
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


def test_report_groups_daily_entry_exit_and_lateness(db):
    employee = UserProfile(
        cognito_sub="attendance-report-sub",
        email="ana@asiati.com.co",
        first_name="Ana",
        last_name="Torres",
        status="ACTIVE",
    )
    db.add(employee)
    db.commit()
    db.refresh(employee)

    site = service.create_site(
        db,
        name="Bogotá",
        code="BOG-REPORT",
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

    # 13:47 UTC = 08:47 America/Bogota, seven minutes after tolerance.
    db.add_all(
        [
            TalentAttendanceEvent(
                employee_id=employee.id,
                site_id=site.id,
                device_id=None,
                event_type="CHECK_IN",
                method="FACE",
                occurred_at=datetime(2026, 10, 5, 13, 47, tzinfo=timezone.utc),
                idempotency_key="report-in",
                recognition_confidence=99.1,
            ),
            TalentAttendanceEvent(
                employee_id=employee.id,
                site_id=site.id,
                device_id=None,
                event_type="CHECK_OUT",
                method="FACE",
                occurred_at=datetime(2026, 10, 5, 23, 0, tzinfo=timezone.utc),
                idempotency_key="report-out",
                recognition_confidence=98.9,
            ),
        ]
    )
    db.commit()

    report = reporting.build_attendance_report(
        db,
        start_date=date(2026, 10, 5),
        end_date=date(2026, 10, 5),
        employee_id=employee.id,
    )

    assert report["summary"]["check_ins"] == 1
    assert report["summary"]["check_outs"] == 1
    assert report["summary"]["late_arrivals"] == 1
    assert report["summary"]["on_time_rate"] == 0.0
    assert report["rows"][0]["employee_name"] == "Ana Torres"
    assert report["rows"][0]["date"] == "2026-10-05"
    assert report["rows"][0]["late_minutes"] == 7
    assert report["rows"][0]["status"] == "LATE"


def test_report_rejects_ranges_over_limit(db):
    with pytest.raises(ValueError):
        reporting.build_attendance_report(
            db,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 6, 1),
        )
