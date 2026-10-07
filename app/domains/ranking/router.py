"""Ranking router — FastAPI endpoints for job rankings."""

from datetime import datetime, timezone
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.deps import get_db, require_permission
from app import crud
from app.domains.candidates import repository as candidates_repository
from app.domains.jobs import reevaluation as reevaluation_repository
from app.infrastructure.imports import queue
from app.domains.ranking.costs import estimate_mass_evaluation_cost
from app.domains.ranking.service import recalculate_ranking, build_latest_ranking
from app.domains.ranking.exceptions import (
    RankingJobNotFound,
    RankingNotFound,
    RankingAlreadyRunning,
)

router = APIRouter(prefix="/api/jobs", tags=["ranking"])
logger = logging.getLogger(__name__)


def _require_job(db: Session, job_id: str, owner_sub: str):
    job = crud.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Vacante no encontrada.")
    return job


@router.get("/{job_id}/ranking/cost-estimate")
def get_mass_evaluation_cost_estimate(
    job_id: str,
    mode: str = Query("fast", pattern=r"^(fast|exhaustive)$"),
    scope: str = Query("all", pattern=r"^(assigned|all)$"),
    candidate_count: int | None = Query(None, ge=1),
    deep_candidate_count: int | None = Query(None, ge=1),
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission("candidates.evaluate")),
):
    job = _require_job(db, job_id, _user["sub"])

    if scope == "all":
        work_mode = str(getattr(job, "work_mode", None) or "ONSITE").upper()
        country_code = str(getattr(job, "country_code", None) or "").strip().upper()

        if work_mode == "REMOTE":
            available = candidates_repository.count_candidates(
                db,
                owner_sub=None,
                include_banned=False,
            )
            total_including_banned = candidates_repository.count_candidates(
                db,
                owner_sub=None,
                include_banned=True,
            )
        elif country_code:
            available = candidates_repository.count_candidates_for_country(
                db,
                country_code=country_code,
                owner_sub=None,
                include_banned=False,
            )
            total_including_banned = candidates_repository.count_candidates_for_country(
                db,
                country_code=country_code,
                owner_sub=None,
                include_banned=True,
            )
        else:
            available = candidates_repository.count_candidates_for_job(
                db,
                job_id=job_id,
                owner_sub=None,
                include_banned=False,
            )
            total_including_banned = candidates_repository.count_candidates_for_job(
                db,
                job_id=job_id,
                owner_sub=None,
                include_banned=True,
            )
    else:
        available = candidates_repository.count_candidates_for_job(
            db,
            job_id=job_id,
            owner_sub=None,
            include_banned=False,
        )
        total_including_banned = candidates_repository.count_candidates_for_job(
            db,
            job_id=job_id,
            owner_sub=None,
            include_banned=True,
        )

    if candidate_count is not None and candidate_count > available:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Solo hay {available} candidatos elegibles para este alcance."
            ),
        )

    selected_count = available if candidate_count is None else candidate_count
    estimate = estimate_mass_evaluation_cost(
        candidate_count=selected_count,
        mode=mode,
        deep_candidate_count=deep_candidate_count,
    )
    estimate.update(
        {
            "job_id": job_id,
            "scope": scope,
            "available_candidate_count": available,
            "excluded_banned_count": max(
                total_including_banned - available,
                0,
            ),
        }
    )
    return estimate


@router.get("/{job_id}/ranking")
def get_job_ranking(
    job_id: str,
    min_score: float = Query(0, ge=0, le=100),
    max_score: float = Query(100, ge=0, le=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    scope: str = Query("assigned", pattern=r"^(assigned|all)$"),
    recommendation: str | None = Query(None),
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission("ranking.read")),
):
    _require_job(db, job_id, _user["sub"])

    if min_score > max_score:
        raise HTTPException(
            status_code=400,
            detail="min_score no puede ser mayor que max_score.",
        )

    return crud.build_ranking_response(
        db,
        job_id,
        page=page,
        page_size=page_size,
        min_score=min_score,
        max_score=max_score,
        recommendation=recommendation,
        scope=scope,
    )


@router.post("/{job_id}/ranking/recalculate")
def recalculate_ranking_endpoint(
    job_id: str,
    mode: str = Query("full", pattern=r"^(full|incremental)$"),
    scope: str = Query("assigned", pattern=r"^(assigned|all)$"),
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission("ranking.recalculate")),
):
    try:
        return recalculate_ranking(
            db,
            job_id=job_id,
            owner_sub=None,
            mode=mode,
            scope=scope,
        )
    except RankingAlreadyRunning as exc:
        raise HTTPException(status_code=409, detail=exc.message)
    except RankingJobNotFound as exc:
        raise HTTPException(status_code=404, detail=exc.message)


def _async_task_payload(task) -> dict:
    return {
        "task_id": task.id,
        "job_id": task.job_id,
        "status": task.status,
        "scope": str(getattr(task, "scope", None) or "assigned"),
        "force_evaluation": bool(getattr(task, "force_evaluation", False)),
        "attempt_count": int(task.attempt_count or 0),
        "last_error_code": task.last_error_code,
        "last_error_message": task.last_error_message,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
    }


@router.post("/{job_id}/ranking/recalculate-async", status_code=202)
def recalculate_ranking_async_endpoint(
    job_id: str,
    mode: str = Query("incremental", pattern=r"^(full|incremental)$"),
    scope: str = Query("all", pattern=r"^(assigned|all)$"),
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission("ranking.recalculate")),
):
    """Queue a durable ranking run so the browser request never holds the LLM loop."""
    job = _require_job(db, job_id, _user["sub"])
    task = reevaluation_repository.schedule_reevaluation(
        db,
        job=job,
        owner_sub=getattr(job, "owner_sub", None) or _user["sub"],
        scope=scope,
        force_evaluation=(mode == "full"),
        restart_terminal=True,
    )
    db.commit()
    db.refresh(task)

    if task.status == "PENDING" and task.queue_dispatched_at is None:
        try:
            queue.send_job_reevaluation(task.id)
        except Exception:
            # The shared worker repairs undispatched durable tasks every cycle.
            logger.exception("Async ranking queue dispatch deferred for task %s", task.id)
            db.rollback()
            task = reevaluation_repository.get_reevaluation_task_by_id(db, task.id)
        else:
            task.queue_dispatched_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(task)

    return _async_task_payload(task)


@router.get("/{job_id}/ranking/recalculate-async/{task_id}")
def get_recalculate_ranking_async_status(
    job_id: str,
    task_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission("ranking.read")),
):
    _require_job(db, job_id, _user["sub"])
    task = reevaluation_repository.get_reevaluation_task_by_id(db, task_id)
    if task is None or str(task.job_id) != str(job_id):
        raise HTTPException(status_code=404, detail="Proceso de ranking no encontrado.")
    return _async_task_payload(task)


@router.get("/{job_id}/ranking/latest")
def get_latest_ranking_endpoint(
    job_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission("ranking.read")),
):
    try:
        return build_latest_ranking(db, job_id=job_id, owner_sub=None)
    except RankingJobNotFound as exc:
        raise HTTPException(status_code=404, detail=exc.message)
    except RankingNotFound as exc:
        raise HTTPException(status_code=404, detail=exc.message)