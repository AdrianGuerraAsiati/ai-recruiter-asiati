"""Explicit, staging-only validation of Odoo contract termination adapter.

This script does not create test employees or use Talent's production database.
The operator must provision one unmistakably synthetic employee + running contract
in the neutralized Odoo staging database before using --execute.
"""
from __future__ import annotations

import argparse
import os
from datetime import date
from urllib.parse import urlparse

from app.domains.odoo_sync.staging import build_staging_client, staging_settings
from app.domains.odoo_sync.termination_delivery import close_contract_and_archive

SENTINEL = "TALENT-E2E-TERMINATION-"
HOST = "asiati-test160526-39554181.dev.odoo.com"
DATABASE = "asiati-test160526-39554181"


def run(*, employee_id: int, effective_date: date, execute: bool, confirm: str) -> dict:
    settings = staging_settings()
    if urlparse(settings.base_url).hostname != HOST or settings.database != DATABASE:
        raise ValueError("Unexpected staging Odoo host or database.")
    if os.getenv("EMPLOYEE_TERMINATION_EXECUTION_ENABLED", "false").lower() == "true":
        raise ValueError("Production termination execution must remain disabled.")
    client = build_staging_client()
    health = client.healthcheck()
    if not health.get("connected") or health.get("uid") != 97:
        raise ValueError("Unexpected staging authentication identity.")

    employees = client.search_read(
        "hr.employee", [["id", "=", employee_id]],
        fields=["id", "name", "active"], limit=2,
        context={"active_test": False},
    )
    if len(employees) != 1 or not str(employees[0].get("name", "")).startswith(SENTINEL):
        raise ValueError("Employee is not an approved synthetic E2E record.")
    contracts = client.search_read(
        "hr.contract", [["employee_id", "=", employee_id]],
        fields=["id", "state", "date_end", "employee_id"], limit=3,
    )
    if len(contracts) != 1:
        raise ValueError("Exactly one synthetic contract is required.")
    owner = contracts[0]["employee_id"]
    if not isinstance(owner, (list, tuple)) or owner[0] != employee_id:
        raise ValueError("Contract does not belong to the synthetic employee.")
    if contracts[0]["state"] not in {"open", "close"}:
        raise ValueError("Unexpected contract state.")
    current_end = contracts[0]["date_end"]
    if contracts[0]["state"] == "close" and current_end != effective_date.isoformat():
        raise ValueError("Contract previously closed with a different effective date.")
    if execute and confirm != f"{SENTINEL}{employee_id}":
        raise ValueError("Explicit confirmation did not match synthetic employee.")

    before = {"employee_active": bool(employees[0]["active"]), "contract_state": contracts[0]["state"],
              "contract_date_end": current_end}
    if not execute:
        return {"mode": "DRY_RUN", "database": settings.database,
                "employee_id": employee_id, "contract_id": contracts[0]["id"],
                "before": before, "would_write": before["employee_active"] or before["contract_state"] == "open"}

    result = close_contract_and_archive(
        client, employee_odoo_id=str(employee_id), effective_date=effective_date,
    )
    # The second call verifies idempotence against real Odoo staging data.
    retry = close_contract_and_archive(
        client, employee_odoo_id=str(employee_id), effective_date=effective_date,
    )
    return {"mode": "E2E_EXECUTED", "database": settings.database,
            "employee_id": employee_id, "contract_id": contracts[0]["id"],
            "before": before, "first": result, "idempotent_retry": retry}


def main() -> None:
    parser = argparse.ArgumentParser(description="Synthetic Odoo staging termination E2E")
    parser.add_argument("--employee-id", required=True, type=int)
    parser.add_argument("--effective-date", required=True, type=date.fromisoformat)
    parser.add_argument("--execute", action="store_true", help="Write ONLY to synthetic Odoo staging records")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()
    if args.employee_id <= 0:
        parser.error("employee-id must be positive")
    print(run(employee_id=args.employee_id, effective_date=args.effective_date,
              execute=args.execute, confirm=args.confirm))


if __name__ == "__main__":
    main()
