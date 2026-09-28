"""Recruitment calendar HTTP routes."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.deps import get_db, require_permission
from app.domains.recruitment_calendar import service
from app.domains.recruitment_calendar.exceptions import (
    RecruitmentApplicationNotEligible,
    RecruitmentEventNotFound,
    RecruitmentEventValidationError,
)
from app.domains.recruitment_calendar.schemas import (
    RecruitmentEventCreate,
    RecruitmentEventUpdate,
)


router = APIRouter(prefix="/api/recruitment-calendar", tags=["recruitment-calendar"])


def _translate(exc: Exception):
    if isinstance(exc, RecruitmentEventNotFound):
        raise HTTPException(status_code=404, detail="Cita no encontrada.")
    if isinstance(exc, RecruitmentApplicationNotEligible):
        raise HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, RecruitmentEventValidationError):
        raise HTTPException(status_code=422, detail=str(exc))
    raise exc


@router.get("/events")
def get_events(
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    job_id: str | None = Query(default=None),
    candidate_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("candidates.read")),
):
    try:
        return {
            "items": service.list_events(
                db,
                starts_before=end,
                ends_after=start,
                job_id=job_id,
                candidate_id=candidate_id,
            )
        }
    except Exception as exc:
        _translate(exc)


@router.get("/applications")
def get_eligible_applications(
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("candidates.read")),
):
    return {"items": service.list_eligible_applications(db)}


@router.post("/events", status_code=201)
def create_event(
    body: RecruitmentEventCreate,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_permission("candidates.manage")),
):
    try:
        return service.create_event(
            db,
            job_id=body.job_id,
            candidate_id=body.candidate_id,
            kind=body.kind,
            starts_at=body.starts_at,
            ends_at=body.ends_at,
            location=body.location,
            notes=body.notes,
            created_by_sub=principal["sub"],
        )
    except Exception as exc:
        _translate(exc)


@router.put("/events/{event_id}")
def update_event(
    event_id: str,
    body: RecruitmentEventUpdate,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("candidates.manage")),
):
    try:
        return service.update_event(
            db,
            event_id,
            changes=body.model_dump(exclude_unset=True),
        )
    except Exception as exc:
        _translate(exc)
