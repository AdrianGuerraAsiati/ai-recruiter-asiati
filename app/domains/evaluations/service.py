"""Evaluation service — orchestrates candidate-job evaluation use cases.

This module contains the business logic for evaluating a candidate against
a job description. It coordinates authorization, retrieval, LLM evaluation,
validation, and persistence while keeping HTTP concerns in the router.
"""

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.domains.candidates import service as candidates_service
from app.domains.candidates.exceptions import CandidateBanned, CandidateNotFound, JobNotFound
from app.domains.evaluations import repository as evaluations_repository
from app.domains.evaluations.rules import (
    normalize_completed_evaluation_result,
    validate_completed_evaluation_result,
)
from app.domains.jobs import repository as jobs_repository
from app.domains.jobs.profile import build_evaluation_text, has_evaluation_criteria

logger = logging.getLogger(__name__)

FAILED_EVALUATION_PUBLIC_MESSAGE = (
    "No fue posible completar la evaluación. Intenta nuevamente."
)
INTERNAL_EVALUATION_ERROR_CODE = "EVALUATION_INTERNAL_ERROR"


class EvaluationCriteriaMissing(RuntimeError):
    """Raised when a vacancy has no recruiter-authored criteria to compare."""


def _safe_failure_code(value: object) -> str:
    candidate = str(value or "").strip()
    if (
        3 <= len(candidate) <= 120
        and all(character.isupper() or character.isdigit() or character == "_" for character in candidate)
    ):
        return candidate
    return "EVALUATION_FAILED"


def evaluate_candidate_evidence(
    *,
    candidate_id: str,
    evaluation_text: str,
) -> tuple[dict[str, Any], str | None]:
    """Run retrieval + LLM evaluation without holding a database session."""
    from app import evaluation as evaluation_backend

    try:
        results = evaluation_backend.retrieve_candidate(
            candidate_id=candidate_id,
            question=evaluation_text,
        )
        llm_result = evaluation_backend.evaluate_candidate(
            candidate_id=candidate_id,
            job_description=evaluation_text,
            results=results,
        )

        if llm_result.get("status", "COMPLETED") == "FAILED":
            return {
                "match_score": 0.0,
                "recommendation": llm_result.get(
                    "recommendation",
                    "EVALUATION_FAILED",
                ),
                "summary": llm_result.get(
                    "summary",
                    FAILED_EVALUATION_PUBLIC_MESSAGE,
                ),
                "strengths": [],
                "gaps": [],
                "requirements": [],
                "status": "FAILED",
                "error_message": _safe_failure_code(
                    llm_result.get("error_message", "EVALUATION_FAILED")
                ),
            }, None

        is_valid, error_msg = validate_completed_evaluation_result(llm_result)
        if not is_valid:
            raise ValueError(error_msg)

        normalized = normalize_completed_evaluation_result(llm_result)
        return {
            "match_score": normalized["match_score"],
            "recommendation": normalized["recommendation"],
            "summary": normalized["summary"],
            "strengths": normalized["strengths"],
            "gaps": normalized["gaps"],
            "requirements": normalized["requirements"],
            "status": "COMPLETED",
            "error_message": None,
        }, None

    except Exception as exc:
        logger.error(
            "LLM evaluation failed for candidate %s: %s",
            candidate_id,
            exc,
            exc_info=True,
        )
        return {
            "match_score": 0.0,
            "recommendation": "EVALUATION_FAILED",
            "summary": FAILED_EVALUATION_PUBLIC_MESSAGE,
            "strengths": [],
            "gaps": [],
            "requirements": [],
            "status": "FAILED",
            "error_message": INTERNAL_EVALUATION_ERROR_CODE,
        }, str(exc)


def persist_candidate_evaluation(
    db: Session,
    *,
    candidate_id: str,
    job_id: str,
    job_evaluation_version: int,
    result: dict[str, Any],
):
    """Persist one normalized evaluation payload."""
    return evaluations_repository.create_evaluation(
        db,
        candidate_id=candidate_id,
        job_id=job_id,
        job_evaluation_version=int(job_evaluation_version),
        match_score=result["match_score"],
        recommendation=result["recommendation"],
        summary=result["summary"],
        strengths=result["strengths"],
        gaps=result["gaps"],
        requirements=result["requirements"],
        status=result["status"],
        error_message=result["error_message"],
    )


def evaluate_candidate_for_owner(
    db: Session,
    *,
    candidate_id: str,
    job_id: str,
    owner_sub: str,
    force: bool = False,
) -> tuple[object, bool, str | None]:
    """Authorize candidate/job access via RBAC, then run the evaluation use case."""
    candidate = candidates_service.require_candidate(
        db,
        candidate_id,
        owner_sub,
    )
    if getattr(candidate, "is_banned", False):
        raise CandidateBanned(candidate_id)

    job = jobs_repository.get_job(db, job_id)
    if job is None:
        raise JobNotFound(job_id)
    if not has_evaluation_criteria(job):
        raise EvaluationCriteriaMissing("JOB_EVALUATION_CRITERIA_MISSING")

    if force:
        return evaluate_candidate_for_job(
            db,
            candidate=candidate,
            job=job,
            force=True,
        )
    return evaluate_candidate_for_job(
        db,
        candidate=candidate,
        job=job,
    )


def evaluate_candidate_for_job(
    db: Session,
    *,
    candidate,
    job,
    force: bool = False,
) -> tuple[object, bool, str | None]:
    """Evaluate a candidate only when its result is stale for this job version."""
    current_job_version = int(getattr(job, "evaluation_version", 1) or 1)
    existing = evaluations_repository.get_evaluation_for_job_candidate(
        db,
        job.id,
        candidate.id,
    )
    if not evaluations_repository.needs_evaluation(
        existing,
        current_job_version=current_job_version,
        force=force,
    ):
        return existing, False, None

    result, internal_error = evaluate_candidate_evidence(
        candidate_id=candidate.id,
        evaluation_text=build_evaluation_text(job),
    )
    evaluation = persist_candidate_evaluation(
        db,
        candidate_id=candidate.id,
        job_id=job.id,
        job_evaluation_version=current_job_version,
        result=result,
    )
    return evaluation, True, internal_error
