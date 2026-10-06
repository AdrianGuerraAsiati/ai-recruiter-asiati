"""Reconcile an active employee roster from the fingerprint clock with Talent.

The source file is intentionally external to the repository because it contains
employee names and clock identifiers. People present in this roster are employees,
not candidates/applicants, and are authoritative as ACTIVE for this reconciliation.

Safe mutations:
- link the fingerprint clock user ID to an employee;
- create a directory-only ACTIVE employee when the roster person is missing;
- reactivate a matched Talent directory employee;
- assign the EMPLOYEE role to newly created directory employees;
- create an attendance setting when needed.

No Cognito account, email, candidate, applicant or Odoo record is invented here.
Existing HR fields such as title, canonical department, company and hire date are
preserved. The report's "Departamento" value stays in the private result because
it may represent a clock grouping rather than the canonical HR department.
"""

from __future__ import annotations

import argparse
import json
import unicodedata
from collections import defaultdict
from pathlib import Path

from app.access_control import EMPLOYEE, assign_role
from app.db import SessionLocal
from app.domains.talent_id.models import (
    TalentEmployeeAttendanceSetting,
    TalentSite,
)
from app.models import UserProfile


def _normalize(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = "".join(
        char for char in normalized if not unicodedata.combining(char)
    )
    return " ".join(ascii_text.upper().split())


def _employee_name(profile: UserProfile) -> str:
    return " ".join(
        part.strip()
        for part in (profile.first_name or "", profile.last_name or "")
        if part and part.strip()
    ).strip()


def _load_source(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("biometric employee source must be a JSON array")
    rows: list[dict] = []
    seen_ids: set[str] = set()
    for item in payload:
        if not isinstance(item, dict):
            continue
        device_user_id = str(item.get("device_user_id") or "").strip()
        name = str(item.get("name") or "").strip()
        if not device_user_id or not name or device_user_id in seen_ids:
            continue
        seen_ids.add(device_user_id)
        rows.append(
            {
                "device_user_id": device_user_id,
                "name": name,
                "department": str(item.get("department") or "").strip(),
                "device_number": str(item.get("device_number") or "").strip(),
            }
        )
    return rows


def _create_active_employee(db, row: dict) -> UserProfile:
    profile = UserProfile(
        cognito_sub=None,
        email=None,
        login_username=None,
        first_name=row["name"],
        last_name=None,
        onboarding_status="NOT_REQUIRED",
        status="ACTIVE",
        created_by_sub="biometric-active-roster",
    )
    db.add(profile)
    db.flush()
    assign_role(
        db,
        profile,
        EMPLOYEE,
        assigned_by_sub="biometric-active-roster",
    )
    return profile


def reconcile(source_rows: list[dict]) -> dict:
    db = SessionLocal()
    try:
        profiles = db.query(UserProfile).all()
        profiles_by_id = {item.id: item for item in profiles}
        profiles_by_name: dict[str, list[UserProfile]] = defaultdict(list)
        for profile in profiles:
            normalized_name = _normalize(_employee_name(profile))
            if normalized_name:
                profiles_by_name[normalized_name].append(profile)

        settings = db.query(TalentEmployeeAttendanceSetting).all()
        settings_by_employee = {item.employee_id: item for item in settings}
        settings_by_biometric_id: dict[str, list[TalentEmployeeAttendanceSetting]] = (
            defaultdict(list)
        )
        for setting in settings:
            biometric_user_id = str(
                getattr(setting, "biometric_user_id", None) or ""
            ).strip()
            if biometric_user_id:
                settings_by_biometric_id[biometric_user_id].append(setting)

        active_sites = (
            db.query(TalentSite)
            .filter(TalentSite.active.is_(True))
            .order_by(TalentSite.created_at.asc())
            .all()
        )
        default_site = active_sites[0] if len(active_sites) == 1 else None

        matched = 0
        linked_by_existing_id = 0
        linked_by_name = 0
        created_employees = 0
        reactivated_employees = 0
        created_attendance_settings = 0
        already_linked = 0
        unmatched: list[dict] = []
        ambiguous: list[dict] = []
        conflicts: list[dict] = []

        for row in source_rows:
            device_user_id = row["device_user_id"]
            linked_settings = settings_by_biometric_id.get(device_user_id, [])

            profile = None
            match_method = None
            if len(linked_settings) == 1:
                profile = profiles_by_id.get(linked_settings[0].employee_id)
                if profile is not None:
                    match_method = "BIOMETRIC_ID"
            elif len(linked_settings) > 1:
                conflicts.append(
                    {
                        **row,
                        "reason": "BIOMETRIC_ID_ALREADY_LINKED_TO_MULTIPLE_EMPLOYEES",
                    }
                )
                continue

            if profile is None:
                normalized_name = _normalize(row["name"])
                name_matches = profiles_by_name.get(normalized_name, [])
                if len(name_matches) == 1:
                    profile = name_matches[0]
                    match_method = "NAME"
                elif len(name_matches) > 1:
                    ambiguous.append({**row, "reason": "AMBIGUOUS_NAME"})
                    continue
                else:
                    profile = _create_active_employee(db, row)
                    profiles_by_id[profile.id] = profile
                    profiles_by_name[normalized_name].append(profile)
                    match_method = "CREATED"
                    created_employees += 1

            if profile.status != "ACTIVE":
                profile.status = "ACTIVE"
                reactivated_employees += 1

            setting = settings_by_employee.get(profile.id)
            if setting is None:
                setting = TalentEmployeeAttendanceSetting(
                    employee_id=profile.id,
                    site_id=default_site.id if default_site else None,
                    schedule_id=None,
                    attendance_eligible=bool(default_site),
                    biometric_user_id=device_user_id,
                )
                db.add(setting)
                settings_by_employee[profile.id] = setting
                settings_by_biometric_id[device_user_id].append(setting)
                created_attendance_settings += 1
            else:
                current_id = str(
                    getattr(setting, "biometric_user_id", None) or ""
                ).strip()
                if current_id and current_id != device_user_id:
                    conflicts.append(
                        {
                            **row,
                            "reason": "EMPLOYEE_HAS_DIFFERENT_BIOMETRIC_ID",
                        }
                    )
                    continue
                if current_id == device_user_id:
                    already_linked += 1
                else:
                    setting.biometric_user_id = device_user_id
                    settings_by_biometric_id[device_user_id].append(setting)

            matched += 1
            if match_method == "BIOMETRIC_ID":
                linked_by_existing_id += 1
            elif match_method == "NAME":
                linked_by_name += 1

        db.commit()
        return {
            "source_people": len(source_rows),
            "matched": matched,
            "active_employees_after_sync": matched,
            "linked_by_existing_id": linked_by_existing_id,
            "linked_by_name": linked_by_name,
            "created_employees": created_employees,
            "reactivated_employees": reactivated_employees,
            "already_linked": already_linked,
            "created_attendance_settings": created_attendance_settings,
            "unmatched_count": len(unmatched),
            "ambiguous_count": len(ambiguous),
            "conflict_count": len(conflicts),
            "single_active_site_available": default_site is not None,
            "unmatched": unmatched,
            "ambiguous": ambiguous,
            "conflicts": conflicts,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()

    source_path = Path(args.source)
    result_path = Path(args.result)
    rows = _load_source(source_path)
    result = reconcile(rows)
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Public CI logs contain counts only; names/clock IDs stay in the private result file.
    print(
        json.dumps(
            {
                key: value
                for key, value in result.items()
                if key not in {"unmatched", "ambiguous", "conflicts"}
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
