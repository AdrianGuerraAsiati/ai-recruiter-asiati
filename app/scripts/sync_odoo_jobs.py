"""Backfill existing Talent vacancies into the Odoo recruitment website."""

from __future__ import annotations

import json

from app.db import SessionLocal
from app.domains.odoo_sync import integration, job_delivery


def sync_existing_jobs(db) -> dict:
    return job_delivery.sync_all_jobs_now(db)


def main() -> None:
    with SessionLocal() as db:
        try:
            result = sync_existing_jobs(db)
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
