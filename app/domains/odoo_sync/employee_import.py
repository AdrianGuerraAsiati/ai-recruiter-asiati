"""Import the Odoo employee directory into Talent.

Odoo is treated as the HR directory source for this operation. Importing a person
must not implicitly create a Cognito account or expose temporary credentials.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.access_control import EMPLOYEE, assign_role
from app.domains.odoo_sync import integration
from app.integrations.odoo.client import OdooClientError
from app.models import UserProfile


class OdooEmployeeImportError(RuntimeError):
    pass


def _text(value: Any) -> str | None:
    if value is None or value is False:
        return None
    normalized = str(value).strip()
    return normalized or None


def _email(value: Any) -> str | None:
    normalized = str(value or "").strip().casefold()
    if normalized.count("@") != 1:
        return None
    local, domain = normalized.split("@", 1)
    if not local or not domain or "." not in domain:
        return None
    return normalized


def _many2one_name(value: Any) -> str | None:
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return _text(value[1])
    return None


def _readable_fields(client) -> dict[str, dict[str, Any]]:
    fields = client.fields_get(
        "hr.employee",
        attributes=("string", "type", "required", "readonly", "relation"),
    )
    return {name: dict(meta or {}) for name, meta in fields.items()}


def _fields_to_read(fields: dict[str, dict[str, Any]]) -> list[str]:
    preferred = (
        "id",
        "name",
        "work_email",
        "job_title",
        "job_id",
        "department_id",
        "company_id",
        "active",
        "first_contract_date",
    )
    return [name for name in preferred if name == "id" or name in fields]


def _all_employee_domain(fields: dict[str, dict[str, Any]]) -> list:
    if "active" not in fields:
        return []
    # Explicitly include archived employees too. Odoo's active_test normally hides them.
    return ["|", ["active", "=", True], ["active", "=", False]]


def _employee_status(row: dict) -> str:
    return "ACTIVE" if row.get("active", True) is not False else "DISABLED"


def _hire_date(row: dict) -> date | None:
    value = _text(row.get("first_contract_date"))
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _job_title(row: dict) -> str | None:
    return _text(row.get("job_title")) or _many2one_name(row.get("job_id"))


def _department(row: dict) -> str | None:
    return _many2one_name(row.get("department_id"))


def _company(row: dict) -> str | None:
    return _many2one_name(row.get("company_id"))


def _find_by_email(db: Session, email: str | None) -> UserProfile | None:
    if not email:
        return None
    return db.query(UserProfile).filter(UserProfile.email == email).one_or_none()


def _apply_odoo_values(
    profile: UserProfile,
    *,
    row: dict,
    imported_email: str | None,
) -> None:
    """Apply directory data without overwriting local identity/access decisions."""

    profile.odoo_employee_id = str(row["id"])

    name = _text(row.get("name"))
    if not profile.cognito_sub:
        # Imported-only profiles preserve Odoo's display name verbatim rather than
        # guessing culturally-specific first/last-name boundaries.
        profile.first_name = name or profile.first_name or f"Empleado Odoo {row['id']}"
        profile.last_name = None
        profile.email = imported_email
        profile.status = _employee_status(row)
        profile.onboarding_status = "NOT_REQUIRED"
        imported_hire_date = _hire_date(row)
        if imported_hire_date is not None:
            profile.hire_date = imported_hire_date
    elif profile.email is None and imported_email:
        profile.email = imported_email

    title = _job_title(row)
    department = _department(row)
    company = _company(row)
    if title is not None:
        profile.job_title = title
    if department is not None:
        profile.department = department
    if company is not None:
        profile.company_name = company


def sync_employees_from_odoo(
    db: Session,
    *,
    client=None,
    actor_sub: str | None = None,
) -> dict:
    """Idempotently import all Odoo hr.employee rows into Talent."""

    transport = client or integration.build_odoo_client()
    try:
        fields = _readable_fields(transport)
        rows = transport.search_read(
            "hr.employee",
            _all_employee_domain(fields),
            fields=_fields_to_read(fields),
        )
    except OdooClientError as exc:
        raise OdooEmployeeImportError(str(exc)) from exc

    normalized_emails = [_email(row.get("work_email")) for row in rows]
    email_counts = Counter(email for email in normalized_emails if email)

    created = 0
    updated = 0
    linked_by_email = 0
    without_email = 0
    duplicate_email_rows = 0
    inactive = 0

    try:
        for row in rows:
            raw_id = row.get("id")
            if raw_id in (None, ""):
                continue
            odoo_id = str(raw_id)
            imported_email = _email(row.get("work_email"))
            if not imported_email:
                without_email += 1
            if imported_email and email_counts[imported_email] > 1:
                duplicate_email_rows += 1
                match_email = None
                safe_email = None
            else:
                match_email = imported_email
                safe_email = imported_email

            profile = (
                db.query(UserProfile)
                .filter(UserProfile.odoo_employee_id == odoo_id)
                .one_or_none()
            )
            if profile is None:
                profile = _find_by_email(db, match_email)
                if profile is not None:
                    linked_by_email += 1

            if profile is None:
                profile = UserProfile(
                    cognito_sub=None,
                    email=safe_email,
                    login_username=None,
                    first_name=_text(row.get("name")) or f"Empleado Odoo {odoo_id}",
                    last_name=None,
                    job_title=_job_title(row),
                    department=_department(row),
                    hire_date=_hire_date(row),
                    onboarding_status="NOT_REQUIRED",
                    status=_employee_status(row),
                    created_by_sub=actor_sub,
                    odoo_employee_id=odoo_id,
                )
                db.add(profile)
                db.flush()
                assign_role(
                    db,
                    profile,
                    EMPLOYEE,
                    assigned_by_sub=actor_sub,
                )
                created += 1
            else:
                _apply_odoo_values(
                    profile,
                    row=row,
                    imported_email=safe_email,
                )
                updated += 1

            if row.get("active", True) is False:
                inactive += 1

        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "source": "ODOO",
        "model": "hr.employee",
        "total": len(rows),
        "created": created,
        "updated": updated,
        "linked_by_email": linked_by_email,
        "without_work_email": without_email,
        "duplicate_email_rows": duplicate_email_rows,
        "inactive": inactive,
    }
