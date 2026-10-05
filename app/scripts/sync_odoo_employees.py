"""Backfill the Odoo employee directory into Talent."""

from __future__ import annotations

import json

from app.db import SessionLocal
from app.domains.odoo_sync import employee_import, integration


def sync_existing_employees(db) -> dict:
    return employee_import.sync_employees_from_odoo(
        db,
        actor_sub="system:odoo-employee-sync",
    )


def main() -> None:
    with SessionLocal() as db:
        try:
            result = sync_existing_employees(db)
        except (integration.OdooDisabled, integration.OdooNotConfigured) as exc:
            print(json.dumps({
                "status": "DEFERRED",
                "reason": str(exc),
            }, ensure_ascii=False))
            return

    print(json.dumps({
        "status": "OK",
        **result,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
