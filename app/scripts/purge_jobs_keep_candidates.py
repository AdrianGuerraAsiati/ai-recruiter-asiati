"""One-shot maintenance: remove every Talent vacancy while preserving candidates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.db import SessionLocal
from app.domains.jobs import repository as jobs_repository
from app.domains.odoo_sync import integration as odoo_integration
from app.domains.odoo_sync import job_delivery
from app.domains.odoo_sync import service as odoo_sync_service
from app.models import Candidate, Job, JobCandidate


CONFIRMATION = "KEEP_CANDIDATES_DELETE_ALL_JOBS"


class JobPurgeError(RuntimeError):
    pass


def _sync_job_removal_from_odoo(db, job: Job) -> list[dict]:
    actions: list[dict] = []

    sync = odoo_sync_service.ensure_job_sync(db, job=job)
    db.commit()
    db.refresh(sync)

    # When an active vacancy has never been bound to an Odoo record, first
    # resolve/adopt its current remote record. This prevents deleting Talent's
    # local link before Odoo knows which hr.job should be withdrawn.
    if str(job.status or "ACTIVE").upper() == "ACTIVE" and not str(
        sync.odoo_record_id or ""
    ).strip():
        initial = job_delivery.sync_job_now(db, job_id=job.id)
        actions.append(
            {
                "job_id": job.id,
                "phase": "bind",
                "action": initial.get("action"),
            }
        )

    if str(job.status or "ACTIVE").upper() != "PAUSED":
        job.status = "PAUSED"
        db.commit()
        db.refresh(job)

    odoo_sync_service.ensure_job_sync(db, job=job)
    db.commit()
    final = job_delivery.sync_job_now(db, job_id=job.id)
    actions.append(
        {
            "job_id": job.id,
            "phase": "withdraw",
            "action": final.get("action"),
        }
    )
    return actions


def purge_jobs_keep_candidates(
    db,
    *,
    synchronize_odoo: bool = True,
) -> dict:
    before_candidates = int(db.query(Candidate).count() or 0)
    jobs = db.query(Job).order_by(Job.created_at.asc(), Job.id.asc()).all()
    job_ids = [job.id for job in jobs]
    before_links = int(db.query(JobCandidate).count() or 0)

    odoo_actions: list[dict] = []
    if synchronize_odoo:
        for job in jobs:
            try:
                odoo_actions.extend(_sync_job_removal_from_odoo(db, job))
            except (
                job_delivery.OdooJobDeliveryError,
                job_delivery.OdooJobSyncNotFound,
                job_delivery.OdooJobSyncConflict,
                odoo_integration.OdooDisabled,
                odoo_integration.OdooNotConfigured,
            ) as exc:
                db.rollback()
                raise JobPurgeError(
                    f"Odoo withdrawal failed for job_id={job.id}: {exc}"
                ) from exc

    deleted_jobs = 0
    for job_id in job_ids:
        deleted, deleted_candidates = jobs_repository.delete_job(
            db,
            job_id,
            owner_sub=None,
            delete_candidates=False,
        )
        if deleted_candidates:
            raise JobPurgeError(
                f"Safety invariant failed: job_id={job_id} deleted candidates."
            )
        if deleted:
            deleted_jobs += 1

    after_candidates = int(db.query(Candidate).count() or 0)
    after_jobs = int(db.query(Job).count() or 0)
    after_links = int(db.query(JobCandidate).count() or 0)

    if after_candidates != before_candidates:
        raise JobPurgeError(
            "Candidate count changed during vacancy purge "
            f"({before_candidates} -> {after_candidates})."
        )
    if after_jobs != 0:
        raise JobPurgeError(
            f"Vacancy purge incomplete: {after_jobs} jobs remain."
        )

    return {
        "status": "OK",
        "jobs_before": len(job_ids),
        "jobs_deleted": deleted_jobs,
        "jobs_after": after_jobs,
        "job_candidate_links_before": before_links,
        "job_candidate_links_after": after_links,
        "candidates_before": before_candidates,
        "candidates_after": after_candidates,
        "candidates_preserved": before_candidates == after_candidates,
        "odoo_actions": odoo_actions,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--result", default="")
    args = parser.parse_args()

    if args.confirm != CONFIRMATION:
        raise SystemExit("Refusing destructive purge without exact confirmation token.")

    result_path = Path(args.result) if args.result else None
    with SessionLocal() as db:
        try:
            result = purge_jobs_keep_candidates(db, synchronize_odoo=True)
        except Exception as exc:
            error = {
                "status": "FAILED",
                "error": str(exc),
            }
            if result_path:
                result_path.write_text(
                    json.dumps(error, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            print(json.dumps(error, ensure_ascii=False))
            raise

    if result_path:
        result_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
