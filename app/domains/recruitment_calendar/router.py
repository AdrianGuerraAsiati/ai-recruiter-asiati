"""Recruitment calendar HTTP routes."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.deps import get_db, require_permission
from app.domains.recruitment_calendar import google, service
from app.domains.recruitment_calendar.exceptions import (
    RecruitmentApplicationNotEligible,
    RecruitmentEventNotFound,
    RecruitmentEventValidationError,
)
from app.domains.recruitment_calendar.schemas import (
    RecruitmentEventCreate,
    RecruitmentEventUpdate,
    GoogleCalendarAccountUpdate,
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


def _google_error(exc: Exception):
    if isinstance(exc, google.GoogleCalendarEmailError):
        raise HTTPException(status_code=422, detail="La cuenta debe pertenecer a un dominio corporativo autorizado.")
    if isinstance(exc, google.GoogleCalendarAuthorizationError):
        raise HTTPException(status_code=403, detail="La cuenta de Google debe coincidir con el correo corporativo configurado.")
    if isinstance(exc, google.GoogleCalendarConfigurationError):
        raise HTTPException(status_code=409, detail="Configura primero la conexión corporativa de Google.")
    if isinstance(exc, google.GoogleCalendarRemoteError):
        raise HTTPException(status_code=502, detail="Google Calendar no respondió correctamente.")
    raise exc


@router.get("/google/status")
def google_calendar_status(
    _principal: dict = Depends(require_permission("candidates.read")),
):
    return google.status()


@router.put("/google/account")
def google_calendar_account(
    body: GoogleCalendarAccountUpdate,
    _principal: dict = Depends(require_permission("integrations.manage")),
):
    try:
        return google.set_target_email(body.email)
    except Exception as exc:
        _google_error(exc)


@router.get("/google/oauth/start")
def google_calendar_start(
    principal: dict = Depends(require_permission("integrations.manage")),
):
    try:
        return google.start_oauth(admin_sub=principal["sub"])
    except Exception as exc:
        _google_error(exc)


@router.get("/google/callback", include_in_schema=False)
def google_calendar_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    # Public OAuth redirect: the signed, single-use state is checked before
    # exchanging a code. Never return codes or tokens to the browser.
    if error or not code or not state:
        return RedirectResponse(google.FRONTEND_RETURN_URL + "?google=error", status_code=303)
    try:
        google.oauth_callback(code=code, state=state)
    except google.GoogleCalendarAuthorizationError:
        return RedirectResponse(
            google.FRONTEND_RETURN_URL + "?google=wrong_account", status_code=303
        )
    except (google.GoogleCalendarRemoteError, google.GoogleCalendarConfigurationError):
        return RedirectResponse(google.FRONTEND_RETURN_URL + "?google=error", status_code=303)
    return RedirectResponse(google.FRONTEND_RETURN_URL + "?google=connected", status_code=303)


@router.post("/google/sync")
def google_calendar_sync(
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("integrations.manage")),
):
    try:
        return google.sync_upcoming(db)
    except Exception as exc:
        _google_error(exc)


@router.delete("/google")
def google_calendar_disconnect(
    _principal: dict = Depends(require_permission("integrations.manage")),
):
    try:
        return google.disconnect()
    except Exception as exc:
        _google_error(exc)
