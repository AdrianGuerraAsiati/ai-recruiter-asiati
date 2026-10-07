"""Application service for Jobs use cases."""

import logging

from sqlalchemy.orm import Session

from app.domains.jobs import repository
from app.domains.jobs.exceptions import JobNotFound
from app.domains.jobs.profile import (
    evaluation_signature,
    normalize_evaluation_profile,
)
from app.domains.jobs.reevaluation import schedule_reevaluation
from app.domains.ranking import repository as ranking_repository


logger = logging.getLogger(__name__)


def _sync_odoo_publication_best_effort(db: Session, job) -> None:
    """Mirror active vacancies to Odoo and withdraw already-published paused ones."""

    from datetime import datetime, timezone

    from app.domains.odoo_sync import integration as odoo_integration
    from app.domains.odoo_sync import job_delivery
    from app.domains.odoo_sync import service as odoo_sync_service
    sync = odoo_sync_service.ensure_job_sync(db, job=job)
    status = str(getattr(job, "status", None) or "ACTIVE").upper()

    # A paused vacancy that has never reached Odoo is already in the desired
    # remote state: absent. Do not create an archived/unpublished hr.job row.
    if status != "ACTIVE" and not str(sync.odoo_record_id or "").strip():
        sync.status = odoo_sync_service.SYNC_SYNCED
        sync.last_error = None
        sync.synced_at = datetime.now(timezone.utc)
        db.commit()
        return

    db.commit()
    try:
        job_delivery.sync_job_now(db, job_id=job.id)
    except (
        job_delivery.OdooJobDeliveryError,
        job_delivery.OdooJobSyncNotFound,
        odoo_integration.OdooDisabled,
        odoo_integration.OdooNotConfigured,
    ):
        logger.warning(
            "Odoo vacancy publication deferred for job_id=%s",
            job.id,
        )


def require_job(db: Session, job_id: str, owner_sub: str):
    # Recruiting records are organization-wide. owner_sub is provenance, not
    # an authorization boundary; RBAC is enforced at the HTTP dependency.
    job = repository.get_job(db, job_id)
    if job is None:
        raise JobNotFound(job_id)
    return job


def list_jobs(db: Session, owner_sub: str):
    jobs = repository.list_jobs(db)
    return [
        (
            job,
            repository.count_candidates_for_job(
                db,
                job.id,
                owner_sub=None,
            ),
        )
        for job in jobs
    ]


def list_jobs_page(
    db: Session,
    *,
    owner_sub: str,
    page: int,
    page_size: int,
    sort: str,
    q: str = "",
    country_code: str = "",
    status: str | None = None,
):
    return repository.list_jobs_page(
        db,
        owner_sub=None,
        page=page,
        page_size=page_size,
        sort=sort,
        q=q,
        country_code=country_code,
        status=status,
    )


def create_job(
    db: Session,
    *,
    title: str,
    description: str | None,
    owner_sub: str,
    indeed_description: str | None = None,
    ai_description: str | None = None,
    active_description_source: str | None = None,
    evaluation_profile: dict | None = None,
    **publication_fields,
):
    kwargs = dict(
        title=title,
        description=description,
        owner_sub=owner_sub,
        **publication_fields,
    )

    source_fields_supplied = any(
        value is not None
        for value in (
            indeed_description,
            ai_description,
            active_description_source,
        )
    )
    if source_fields_supplied:
        source = active_description_source or "indeed"
        original = indeed_description if indeed_description is not None else description
        ai_value = ai_description
        effective = ai_value if source == "ai" else original
        if effective is None:
            effective = description
        kwargs.update(
            description=effective,
            indeed_description=original,
            ai_description=ai_value,
            active_description_source=source,
        )

    if evaluation_profile is not None:
        kwargs["evaluation_profile"] = normalize_evaluation_profile(evaluation_profile)
    job = repository.create_job(db, **kwargs)
    _sync_odoo_publication_best_effort(db, job)
    return job


def update_job(
    db: Session,
    *,
    job_id: str,
    owner_sub: str,
    title: str | None = None,
    description: str | None = None,
    indeed_description: str | None = None,
    ai_description: str | None = None,
    active_description_source: str | None = None,
    evaluation_profile: dict | None = None,
    **publication_fields,
):
    job = require_job(db, job_id, owner_sub)

    # Backward-compatible path for lightweight domain fakes that predate job
    # intelligence. Real ORM Job objects always have these fields after 008.
    if not hasattr(job, "evaluation_version"):
        return repository.update_job(
            db,
            job,
            title=title,
            description=description,
            **publication_fields,
        )

    current_profile = normalize_evaluation_profile(
        getattr(job, "evaluation_profile", None)
    )
    next_title = job.title if title is None else title

    current_source = getattr(job, "active_description_source", None) or "indeed"
    current_indeed_description = getattr(job, "indeed_description", None)
    current_ai_description = getattr(job, "ai_description", None)
    if current_indeed_description is None and current_source == "indeed":
        current_indeed_description = job.description
    if current_ai_description is None and current_source == "ai":
        current_ai_description = job.description

    source_fields_supplied = any(
        value is not None
        for value in (
            indeed_description,
            ai_description,
            active_description_source,
        )
    )
    next_source = current_source if active_description_source is None else active_description_source
    next_indeed_description = (
        current_indeed_description
        if indeed_description is None
        else indeed_description
    )
    next_ai_description = (
        current_ai_description
        if ai_description is None
        else ai_description
    )

    # Compatibility for clients that still update only `description`: mutate
    # the currently active source instead of discarding the source model.
    if not source_fields_supplied and description is not None:
        if current_source == "ai":
            next_ai_description = description
        else:
            next_indeed_description = description

    next_description = (
        next_ai_description
        if next_source == "ai"
        else next_indeed_description
    )
    if next_description is None:
        next_description = job.description if description is None else description

    next_profile = (
        current_profile
        if evaluation_profile is None
        else normalize_evaluation_profile(evaluation_profile)
    )

    current_country = str(getattr(job, "country_code", None) or "").strip().upper()
    current_work_mode = str(getattr(job, "work_mode", None) or "ONSITE").strip().upper()
    requested_country = publication_fields.get("country_code")
    requested_work_mode = publication_fields.get("work_mode")
    next_country = (
        current_country
        if requested_country is None
        else str(requested_country or "").strip().upper()
    )
    next_work_mode = (
        current_work_mode
        if requested_work_mode is None
        else str(requested_work_mode or "ONSITE").strip().upper()
    )
    ranking_pool_changed = (
        current_country != next_country
        or current_work_mode != next_work_mode
    )

    old_signature = evaluation_signature(
        job.title,
        job.description,
        current_profile,
    )
    new_signature = evaluation_signature(
        next_title,
        next_description,
        next_profile,
    )
    evaluation_changed = old_signature != new_signature
    next_version = int(getattr(job, "evaluation_version", 1) or 1)
    if evaluation_changed:
        next_version += 1

    try:
        updated = repository.update_job(
            db,
            job,
            title=title,
            description=next_description,
            indeed_description=next_indeed_description,
            ai_description=next_ai_description,
            active_description_source=next_source,
            evaluation_profile=(next_profile if evaluation_profile is not None else None),
            evaluation_version=next_version,
            commit=False,
            **publication_fields,
        )

        candidate_count = repository.count_candidates_for_job(
            db,
            updated.id,
            owner_sub=None,
        )
        reevaluation_scheduled = False
        if evaluation_changed and candidate_count > 0:
            schedule_reevaluation(
                db,
                job=updated,
                owner_sub=getattr(updated, "owner_sub", None) or owner_sub,
            )
            reevaluation_scheduled = True

        if ranking_pool_changed:
            ranking_repository.delete_ranking_for_job(
                db,
                job_id=updated.id,
                commit=False,
            )

        # The job version, reevaluation task and any ranking invalidation are
        # committed as one transaction.
        db.commit()
        db.refresh(updated)
    except Exception:
        db.rollback()
        raise

    _sync_odoo_publication_best_effort(db, updated)

    # Transient response metadata; these values are not persisted on the Job.
    updated._evaluation_changed = evaluation_changed
    updated._reevaluation_scheduled = reevaluation_scheduled
    updated._reevaluation_candidate_count = candidate_count
    return updated


def delete_job(
    db: Session,
    *,
    job_id: str,
    owner_sub: str,
    delete_candidates: bool,
) -> int:
    require_job(db, job_id, owner_sub)
    success, deleted_count = repository.delete_job(
        db,
        job_id,
        owner_sub=None,
        delete_candidates=delete_candidates,
    )
    if not success:
        raise JobNotFound(job_id)
    return deleted_count
