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

@router.get("/coverage/summary")
def get_talent_coverage_summary(
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission("ranking.read")),
):
    """Read-only coverage from valid stored evaluations; never invokes AI."""
    from app.models import Job, Candidate, Evaluation

    jobs = db.query(Job).filter(Job.status == "ACTIVE").all()
    by_job = {job.id: {"job_id": job.id, "title": job.title, "viable": 0,
                        "strong": 0, "evaluated": 0, "last_evaluated_at": None}
              for job in jobs}
    if jobs:
        rows = (
            db.query(Evaluation, Candidate, Job)
            .join(Candidate, Evaluation.candidate_id == Candidate.id)
            .join(Job, Evaluation.job_id == Job.id)
            .filter(
                Job.status == "ACTIVE",
                Candidate.is_banned.is_(False),
                Evaluation.status == "COMPLETED",
                Evaluation.job_evaluation_version == Job.evaluation_version,
            )
            .all()
        )
        for evaluation, candidate, job in rows:
            if job.work_mode != "REMOTE" and (
                not job.country_code
                or not candidate.country_code
                or job.country_code.upper() != candidate.country_code.upper()
            ):
                continue
            item = by_job[job.id]
            item["evaluated"] += 1
            score = float(evaluation.match_score or 0)
            if score >= 70:
                item["viable"] += 1
            if score >= 80:
                item["strong"] += 1
            evaluated_at = evaluation.created_at
            if evaluated_at and (
                item["last_evaluated_at"] is None
                or evaluated_at > item["last_evaluated_at"]
            ):
                item["last_evaluated_at"] = evaluated_at

    counts = {"covered": 0, "strong": 0, "low": 0, "critical": 0, "pending": 0}
    total_viable = 0
    for item in by_job.values():
        total_viable += item["viable"]
        if item["evaluated"] == 0:
            state = "pending"
        elif item["strong"] >= 3:
            state = "strong"
        elif item["viable"] >= 3:
            state = "covered"
        elif item["viable"] >= 1:
            state = "low"
        else:
            state = "critical"
        item["status"] = state
        counts[state] += 1
        if state == "strong":
            counts["covered"] += 1
        if item["last_evaluated_at"]:
            item["last_evaluated_at"] = item["last_evaluated_at"].isoformat()

    total = len(jobs)
    covered = counts["covered"]
    return {
        "total_active_jobs": total,
        "covered_jobs": covered,
        "coverage_percent": round(covered * 100 / total) if total else 0,
        "pipeline_depth": round(total_viable / total, 1) if total else 0,
        "counts": counts,
        "jobs": sorted(by_job.values(), key=lambda row: (
            {"critical": 0, "low": 1, "pending": 2, "covered": 3, "strong": 4}[row["status"]],
            row["title"].lower(),
        )),
    }

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

    requested_force = mode == "full"
    task_scope = str(getattr(task, "scope", None) or "assigned").strip().lower()
    task_force = bool(getattr(task, "force_evaluation", False))
    if task.status in {"PROCESSING", "RANKING"} and (
        task_scope != scope or (requested_force and not task_force)
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "Ya existe una evaluación en curso para esta vacante con otro alcance. "
                "Espera a que termine y vuelve a iniciar el ranking."
            ),
        )

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