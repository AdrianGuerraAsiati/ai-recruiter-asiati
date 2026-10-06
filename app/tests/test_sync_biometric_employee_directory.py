"""Coverage for active employee roster reconciliation."""

import json
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.access_control import EMPLOYEE
from app.db import Base
from app.domains.talent_id.models import TalentEmployeeAttendanceSetting, TalentSite
from app.models import UserProfile
from app.scripts import sync_biometric_employee_directory as sync


def _session_factory(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    monkeypatch.setattr(sync, "SessionLocal", Session)
    return engine, Session


def test_load_source_and_normalization(tmp_path):
    path = tmp_path / "source.json"
    path.write_text(
        json.dumps(
            [
                {
                    "device_user_id": " 13 ",
                    "name": " Petrona Torres Díaz ",
                    "department": "ASIATI HOLDING",
                    "device_number": 2,
                },
                {"device_user_id": "13", "name": "Duplicado"},
                {"device_user_id": "", "name": "Sin id"},
                "invalid",
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    assert sync._normalize("  Pérez  Muñoz ") == "PEREZ MUNOZ"
    assert sync._load_source(path) == [
        {
            "device_user_id": "13",
            "name": "Petrona Torres Díaz",
            "department": "ASIATI HOLDING",
            "device_number": "2",
        }
    ]


def test_load_source_rejects_non_array(tmp_path):
    path = tmp_path / "source.json"
    path.write_text('{"device_user_id":"13"}', encoding="utf-8")

    try:
        sync._load_source(path)
    except ValueError as exc:
        assert "JSON array" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_reconcile_matches_reactivates_and_creates_active_employee(monkeypatch):
    engine, Session = _session_factory(monkeypatch)
    db = Session()
    try:
        site = TalentSite(
            name="Bogotá Principal",
            code="BOG",
            timezone="America/Bogota",
            active=True,
        )
        by_name = UserProfile(
            first_name="Petrona Torres",
            last_name="Díaz",
            department="Talento Humano",
            status="ACTIVE",
        )
        by_id = UserProfile(
            first_name="Nombre Actual",
            last_name="Empleado",
            department="Operaciones",
            status="DISABLED",
        )
        db.add_all([site, by_name, by_id])
        db.commit()
        db.refresh(site)
        db.refresh(by_name)
        db.refresh(by_id)
        db.add(
            TalentEmployeeAttendanceSetting(
                employee_id=by_id.id,
                site_id=site.id,
                attendance_eligible=True,
                biometric_user_id="9001",
            )
        )
        db.commit()

        result = sync.reconcile(
            [
                {
                    "device_user_id": "13",
                    "name": "PETRONA TORRES DIAZ",
                    "department": "ASIATI HOLDING",
                    "device_number": "2",
                },
                {
                    "device_user_id": "9001",
                    "name": "NOMBRE ANTIGUO",
                    "department": "ASIATI HOLDING",
                    "device_number": "2",
                },
                {
                    "device_user_id": "88",
                    "name": "PERSONA AUSENTE",
                    "department": "ASIATI HOLDING",
                    "device_number": "2",
                },
            ]
        )

        assert result["source_people"] == 3
        assert result["matched"] == 3
        assert result["active_employees_after_sync"] == 3
        assert result["linked_by_name"] == 1
        assert result["linked_by_existing_id"] == 1
        assert result["created_employees"] == 1
        assert result["reactivated_employees"] == 1
        assert result["created_attendance_settings"] == 2
        assert result["unmatched_count"] == 0
        assert result["ambiguous_count"] == 0
        assert result["conflict_count"] == 0
        assert result["single_active_site_available"] is True

        verify = Session()
        try:
            existing = verify.get(UserProfile, by_name.id)
            reactivated = verify.get(UserProfile, by_id.id)
            created = (
                verify.query(UserProfile)
                .filter(UserProfile.first_name == "PERSONA AUSENTE")
                .one()
            )
            setting = (
                verify.query(TalentEmployeeAttendanceSetting)
                .filter(TalentEmployeeAttendanceSetting.employee_id == by_name.id)
                .one()
            )
            created_setting = (
                verify.query(TalentEmployeeAttendanceSetting)
                .filter(TalentEmployeeAttendanceSetting.employee_id == created.id)
                .one()
            )

            assert existing.department == "Talento Humano"
            assert reactivated.status == "ACTIVE"
            assert created.status == "ACTIVE"
            assert created.email is None
            assert created.cognito_sub is None
            assert created.onboarding_status == "NOT_REQUIRED"
            assert {role.role_code for role in created.role_assignments} == {EMPLOYEE}
            assert setting.biometric_user_id == "13"
            assert created_setting.biometric_user_id == "88"
            assert created_setting.site_id == site.id
            assert created_setting.attendance_eligible is True
        finally:
            verify.close()
    finally:
        db.close()
        engine.dispose()


def test_reconcile_reports_ambiguous_and_biometric_conflict(monkeypatch):
    engine, Session = _session_factory(monkeypatch)
    db = Session()
    try:
        conflict = UserProfile(
            first_name="Empleado",
            last_name="Conflicto",
            status="DISABLED",
        )
        ambiguous_a = UserProfile(
            first_name="Nombre",
            last_name="Duplicado",
            status="ACTIVE",
        )
        ambiguous_b = UserProfile(
            first_name="Nombre Duplicado",
            last_name=None,
            status="ACTIVE",
        )
        db.add_all([conflict, ambiguous_a, ambiguous_b])
        db.commit()
        db.refresh(conflict)
        db.add(
            TalentEmployeeAttendanceSetting(
                employee_id=conflict.id,
                attendance_eligible=True,
                biometric_user_id="OLD-ID",
            )
        )
        db.commit()

        result = sync.reconcile(
            [
                {
                    "device_user_id": "NEW-ID",
                    "name": "EMPLEADO CONFLICTO",
                    "department": "",
                    "device_number": "2",
                },
                {
                    "device_user_id": "77",
                    "name": "NOMBRE DUPLICADO",
                    "department": "",
                    "device_number": "2",
                },
            ]
        )

        assert result["matched"] == 0
        assert result["created_employees"] == 0
        assert result["reactivated_employees"] == 1
        assert result["unmatched_count"] == 0
        assert result["ambiguous_count"] == 1
        assert result["conflict_count"] == 1
        assert result["ambiguous"][0]["reason"] == "AMBIGUOUS_NAME"
        assert result["conflicts"][0]["reason"] == "EMPLOYEE_HAS_DIFFERENT_BIOMETRIC_ID"
        assert result["single_active_site_available"] is False

        verify = Session()
        try:
            assert verify.get(UserProfile, conflict.id).status == "ACTIVE"
        finally:
            verify.close()
    finally:
        db.close()
        engine.dispose()


def test_reconcile_detects_duplicate_biometric_id(monkeypatch):
    engine, Session = _session_factory(monkeypatch)
    db = Session()
    try:
        first = UserProfile(first_name="Primero", status="ACTIVE")
        second = UserProfile(first_name="Segundo", status="ACTIVE")
        db.add_all([first, second])
        db.commit()
        db.refresh(first)
        db.refresh(second)
        db.add_all(
            [
                TalentEmployeeAttendanceSetting(
                    employee_id=first.id,
                    attendance_eligible=True,
                    biometric_user_id="DUP",
                ),
                TalentEmployeeAttendanceSetting(
                    employee_id=second.id,
                    attendance_eligible=True,
                    biometric_user_id="DUP",
                ),
            ]
        )
        db.commit()

        result = sync.reconcile(
            [
                {
                    "device_user_id": "DUP",
                    "name": "CUALQUIER NOMBRE",
                    "department": "",
                    "device_number": "2",
                }
            ]
        )

        assert result["conflict_count"] == 1
        assert (
            result["conflicts"][0]["reason"]
            == "BIOMETRIC_ID_ALREADY_LINKED_TO_MULTIPLE_EMPLOYEES"
        )
    finally:
        db.close()
        engine.dispose()


def test_main_writes_private_result_file(monkeypatch, tmp_path, capsys):
    source = tmp_path / "source.json"
    result_path = tmp_path / "result.json"
    source.write_text(
        json.dumps(
            [
                {
                    "device_user_id": "13",
                    "name": "PERSONA",
                    "department": "ASIATI HOLDING",
                    "device_number": "2",
                }
            ]
        ),
        encoding="utf-8",
    )
    expected = {
        "source_people": 1,
        "matched": 1,
        "active_employees_after_sync": 1,
        "linked_by_existing_id": 0,
        "linked_by_name": 0,
        "created_employees": 1,
        "reactivated_employees": 0,
        "already_linked": 0,
        "created_attendance_settings": 1,
        "unmatched_count": 0,
        "ambiguous_count": 0,
        "conflict_count": 0,
        "single_active_site_available": False,
        "unmatched": [],
        "ambiguous": [],
        "conflicts": [],
    }
    monkeypatch.setattr(sync, "reconcile", lambda _rows: expected)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "sync_biometric_employee_directory",
            "--source",
            str(source),
            "--result",
            str(result_path),
        ],
    )

    sync.main()

    saved = json.loads(result_path.read_text(encoding="utf-8"))
    assert saved == expected
    public_output = capsys.readouterr().out
    assert "PERSONA" not in public_output
    assert '"created_employees": 1' in public_output
