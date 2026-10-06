"""Biometric clock report import coverage."""

import struct
from datetime import date, datetime, time

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.db import Base
from app.domains.talent_id import attendance_import, reporting, service
from app.domains.talent_id.models import (
    TalentAttendanceEvent,
    TalentEmployeeAttendanceSetting,
)
from app.models import UserProfile


def _label_record(row: int, column: int, value: str) -> bytes:
    encoded = value.encode("utf-16le")
    payload = struct.pack("<HHHHB", row, column, 0, len(value), 1) + encoded
    return struct.pack("<HH", 0x0204, len(payload)) + payload


def _number_record(row: int, column: int, value: float) -> bytes:
    payload = struct.pack("<HHHd", row, column, 0, value)
    return struct.pack("<HH", 0x0203, len(payload)) + payload


def test_biff_cell_reader_handles_inline_unicode_and_numbers():
    stream = b"".join(
        [
            _label_record(0, 0, "Nombre"),
            _label_record(1, 0, "PETRONA TORRES DÍAZ"),
            _number_record(1, 1, 46013.34494212963),
        ]
    )

    cells = attendance_import._parse_biff_cells(stream)

    assert cells[(0, 0)] == "Nombre"
    assert cells[(1, 0)] == "PETRONA TORRES DÍAZ"
    assert cells[(1, 1)] == 46013.34494212963


def test_import_report_matches_employee_dedupes_and_surfaces_unknown_codes(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        employee = UserProfile(
            cognito_sub="report-employee-sub",
            email="petrona@asiati.com.co",
            first_name="Petrona Torres",
            last_name="Díaz",
            status="ACTIVE",
        )
        db.add(employee)
        db.commit()
        db.refresh(employee)

        site = service.create_site(
            db,
            name="Bogotá Principal",
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

        source_rows = [
            attendance_import.AttendanceReportRow(
                device_user_id="13",
                employee_name="PETRONA TORRES DIAZ",
                occurred_local=datetime(2026, 1, 5, 8, 16, 43),
                device_number="2",
                record_code="0",
                department="ASIATI HOLDING",
                source_row=2,
            ),
            attendance_import.AttendanceReportRow(
                device_user_id="13",
                employee_name="PETRONA TORRES DIAZ",
                occurred_local=datetime(2026, 1, 5, 17, 51, 22),
                device_number="2",
                record_code="1",
                department="ASIATI HOLDING",
                source_row=3,
            ),
            # Exact duplicate of the first attendance row.
            attendance_import.AttendanceReportRow(
                device_user_id="13",
                employee_name="PETRONA TORRES DIAZ",
                occurred_local=datetime(2026, 1, 5, 8, 16, 43),
                device_number="2",
                record_code="0",
                department="ASIATI HOLDING",
                source_row=4,
            ),
            attendance_import.AttendanceReportRow(
                device_user_id="13",
                employee_name="PETRONA TORRES DIAZ",
                occurred_local=datetime(2026, 1, 5, 12, 0, 0),
                device_number="2",
                record_code="2",
                department="ASIATI HOLDING",
                source_row=5,
            ),
            attendance_import.AttendanceReportRow(
                device_user_id="99",
                employee_name="PERSONA NO REGISTRADA",
                occurred_local=datetime(2026, 1, 5, 9, 0, 0),
                device_number="2",
                record_code="0",
                department="ASIATI HOLDING",
                source_row=6,
            ),
        ]
        monkeypatch.setattr(
            attendance_import,
            "parse_biometric_xls",
            lambda _raw: source_rows,
        )

        result = attendance_import.import_biometric_report(
            db,
            raw=b"fake-xls",
            site_id=site.id,
            created_by_sub="admin-sub",
            filename="REPORTE ENERO.xls",
        )

        assert result["rows_total"] == 5
        assert result["source_users"] == 2
        assert result["matched_employees"] == 1
        assert result["imported_events"] == 2
        assert result["duplicate_events"] == 1
        assert result["unsupported_rows"] == 1
        assert result["unsupported_codes"] == {"2": 1}
        assert result["unmatched_rows"] == 1
        assert result["unmatched_people"][0]["name"] == "PERSONA NO REGISTRADA"

        events = (
            db.query(TalentAttendanceEvent)
            .order_by(TalentAttendanceEvent.occurred_at.asc())
            .all()
        )
        assert [event.event_type for event in events] == ["CHECK_IN", "CHECK_OUT"]
        assert all(attendance_import.is_report_event(event) for event in events)
        assert events[0].occurred_at.hour == 13  # 08:16 in Bogotá stored as UTC.

        attendance_setting = (
            db.query(TalentEmployeeAttendanceSetting)
            .filter(TalentEmployeeAttendanceSetting.employee_id == employee.id)
            .one()
        )
        assert attendance_setting.biometric_user_id == "13"

        report = reporting.build_attendance_report(
            db,
            start_date=date(2026, 1, 5),
            end_date=date(2026, 1, 5),
        )
        assert report["summary"]["report_events"] == 2
        assert report["summary"]["manual_events"] == 0
        assert report["rows"][0]["check_in_method"] == "REPORT"
        assert report["rows"][0]["check_out_method"] == "REPORT"

        second = attendance_import.import_biometric_report(
            db,
            raw=b"fake-xls",
            site_id=site.id,
            created_by_sub="admin-sub",
            filename="REPORTE ENERO.xls",
        )
        assert second["imported_events"] == 0
        assert second["duplicate_events"] == 3
    finally:
        db.close()
        engine.dispose()



def test_import_report_prefers_biometric_id_for_historical_employee(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        employee = UserProfile(
            cognito_sub="historical-sub",
            email="historical@asiati.com.co",
            first_name="Nombre Actual",
            last_name="Distinto",
            status="DISABLED",
        )
        db.add(employee)
        db.commit()
        db.refresh(employee)

        site = service.create_site(
            db,
            name="Bogotá Histórica",
            code="BOG-HIST",
            timezone_name="America/Bogota",
        )
        schedule = service.create_schedule(
            db,
            name="Histórico",
            start_time=time(8, 0),
            end_time=time(17, 0),
            tolerance_minutes=0,
        )
        setting = service.configure_employee_attendance(
            db,
            employee_id=employee.id,
            site_id=site.id,
            schedule_id=schedule.id,
            attendance_eligible=True,
        )
        setting.biometric_user_id = "9001"
        db.commit()

        monkeypatch.setattr(
            attendance_import,
            "parse_biometric_xls",
            lambda _raw: [
                attendance_import.AttendanceReportRow(
                    device_user_id="9001",
                    employee_name="NOMBRE ANTIGUO EN EL RELOJ",
                    occurred_local=datetime(2026, 1, 3, 8, 0, 0),
                    device_number="2",
                    record_code="0",
                    department="ASIATI HOLDING",
                    source_row=2,
                )
            ],
        )

        result = attendance_import.import_biometric_report(
            db,
            raw=b"fake-xls",
            site_id=site.id,
            created_by_sub="admin-sub",
            filename="historico.xls",
        )

        assert result["matched_employees"] == 1
        assert result["imported_events"] == 1
        event = db.query(TalentAttendanceEvent).one()
        assert event.employee_id == employee.id
    finally:
        db.close()
        engine.dispose()
