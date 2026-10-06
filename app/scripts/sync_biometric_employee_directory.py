"""Reconcile biometric-clock identities with existing Talent employees.

The source file is intentionally external to the repository because it contains
employee names and biometric-clock identifiers. Odoo/Talent remain the canonical
HR directory: this script never creates, reactivates, or disables employees.

Safe mutations:
- bind the clock's user ID to a uniquely matched Talent employee;
- create an attendance setting only when needed;
- fill department only when the Talent profile has no department.

Everything else is preserved.
"""

from __future__ import annotations

import argparse
import json
import unicodedata
from collections import defaultdict
from pathlib import Path

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
        created_attendance_settings = 0
        departments_filled = 0
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
                name_matches = profiles_by_name.get(_normalize(row["name"]), [])
                if len(name_matches) == 1:
                    profile = name_matches[0]
                    match_method = "NAME"
                elif len(name_matches) > 1:
                    ambiguous.append({**row, "reason": "AMBIGUOUS_NAME"})
                    continue
                else:
                    unmatched.append({**row, "reason": "NO_TALENT_EMPLOYEE"})
                    continue

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

            if not (profile.department or "").strip() and row["department"]:
                profile.department = row["department"]
                departments_filled += 1

            matched += 1
            if match_method == "BIOMETRIC_ID":
                linked_by_existing_id += 1
            elif match_method == "NAME":
                linked_by_name += 1

        db.commit()
        return {
            "source_people": len(source_rows),
            "matched": matched,
            "linked_by_existing_id": linked_by_existing_id,
            "linked_by_name": linked_by_name,
            "already_linked": already_linked,
            "created_attendance_settings": created_attendance_settings,
            "departments_filled": departments_filled,
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
