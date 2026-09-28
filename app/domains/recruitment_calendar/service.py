"""Recruitment calendar business rules."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.domains.recruitment_calendar import repository
from app.domains.recruitment_calendar.exceptions import (
    RecruitmentApplicationNotEligible,
    RecruitmentEventNotFound,
    RecruitmentEventValidationError,
)
from app.models import RecruitmentEvent


ELIGIBLE_APPLICATION_STATUSES = {"SELECTED", "INTERVIEW", "OFFER", "HIRED"}
EVENT_KINDS = {"PHONE_CALL", "ONSITE_INTERVIEW"}
EVENT_STATUSES = {"SCHEDULED", "COMPLETED", "CANCELED"}


def _validate_window(starts_at: datetime, ends_at: datetime) -> None:
    if starts_at.tzinfo is None or ends_at.tzinfo is None:
        raise RecruitmentEventValidationError("La fecha y hora deben incluir zona horaria.")
    if ends_at <= starts_at:
        raise RecruitmentEventValidationError("La hora final debe ser posterior a la inicial.")


def _persisted_datetime(value: datetime) -> datetime:
    """Normalize dialects such as SQLite that drop timezone metadata on read."""

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _require_application(db: Session, *, job_id: str, candidate_id: str):
    application = repository.get_application(
        db,
        job_id=job_id,
        candidate_id=candidate_id,
    )
    if application is None:
        raise RecruitmentApplicationNotEligible(
            "El candidato no pertenece a la vacante seleccionada."
        )
    return application


def _event_payload(event: RecruitmentEvent) -> dict:
    return {
        "id": event.id,
        "job_id": event.job_id,
        "candidate_id": event.candidate_id,
        "kind": event.kind,
        "starts_at": event.starts_at.isoformat(),
        "ends_at": event.ends_at.isoformat(),
        "location": event.location,
        "notes": event.notes,
        "status": event.status,
        "created_by_sub": event.created_by_sub,
        "created_at": event.created_at.isoformat() if event.created_at else None,
        "updated_at": event.updated_at.isoformat() if event.updated_at else None,
        "candidate": {
            "candidate_id": event.candidate.id,
            "name": event.candidate.name,
            "email": event.candidate.email,
        },
        "job": {
            "job_id": event.job.id,
            "title": event.job.title,
        },
    }


def application_payload(link, candidate, job) -> dict:
    return {
        "id": link.id,
        "application_status": link.application_status,
        "candidate": {
            "candidate_id": candidate.id,
            "name": candidate.name,
            "email": candidate.email,
        },
        "job": {
            "job_id": job.id,
            "title": job.title,
        },
    }


def list_events(
    db: Session,
    *,
    starts_before: datetime | None = None,
    ends_after: datetime | None = None,
    job_id: str | None = None,
    candidate_id: str | None = None,
) -> list[dict]:
    return [
        _event_payload(event)
        for event in repository.list_events(
            db,
            starts_before=starts_before,
            ends_after=ends_after,
            job_id=job_id,
            candidate_id=candidate_id,
        )
    ]


def list_eligible_applications(db: Session) -> list[dict]:
    return [
        application_payload(link, candidate, job)
        for link, candidate, job in repository.list_eligible_applications(db)
    ]


def create_event(
    db: Session,
    *,
    job_id: str,
    candidate_id: str,
    kind: str,
    starts_at: datetime,
    ends_at: datetime,
    location: str | None,
    notes: str | None,
    created_by_sub: str,
) -> dict:
    application = _require_application(db, job_id=job_id, candidate_id=candidate_id)
    if application.application_status not in ELIGIBLE_APPLICATION_STATUSES:
        raise RecruitmentApplicationNotEligible(
            "Selecciona al candidato antes de agendar una llamada o entrevista."
        )
    if kind not in EVENT_KINDS:
        raise RecruitmentEventValidationError("Tipo de cita no válido.")
    _validate_window(starts_at, ends_at)

    event = RecruitmentEvent(
        job_id=job_id,
        candidate_id=candidate_id,
        kind=kind,
        starts_at=starts_at,
        ends_at=ends_at,
        location=(location or "").strip() or None,
        notes=(notes or "").strip() or None,
        status="SCHEDULED",
        created_by_sub=created_by_sub,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return _event_payload(event)


def update_event(db: Session, event_id: str, *, changes: dict) -> dict:
    event = repository.get_event(db, event_id)
    if event is None:
        raise RecruitmentEventNotFound()

    next_kind = changes.get("kind", event.kind)
    next_status = changes.get("status", event.status)
    next_start = changes.get("starts_at") or _persisted_datetime(event.starts_at)
    next_end = changes.get("ends_at") or _persisted_datetime(event.ends_at)
    if next_kind not in EVENT_KINDS:
        raise RecruitmentEventValidationError("Tipo de cita no válido.")
    if next_status not in EVENT_STATUSES:
        raise RecruitmentEventValidationError("Estado de cita no válido.")
    _validate_window(next_start, next_end)

    for field in ("kind", "starts_at", "ends_at", "status"):
        if field in changes and changes[field] is not None:
            setattr(event, field, changes[field])
    for field in ("location", "notes"):
        if field in changes:
            value = changes[field]
            setattr(event, field, (value or "").strip() or None)

    db.commit()
    db.refresh(event)
    return _event_payload(event)
