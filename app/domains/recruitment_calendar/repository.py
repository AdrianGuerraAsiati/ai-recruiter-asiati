"""Persistence helpers for recruitment calendar events."""

from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Candidate, Job, JobCandidate, RecruitmentEvent


def get_application(db: Session, *, job_id: str, candidate_id: str) -> JobCandidate | None:
    return (
        db.query(JobCandidate)
        .filter(
            JobCandidate.job_id == job_id,
            JobCandidate.candidate_id == candidate_id,
        )
        .one_or_none()
    )


def get_event(db: Session, event_id: str) -> RecruitmentEvent | None:
    return db.query(RecruitmentEvent).filter(RecruitmentEvent.id == event_id).one_or_none()


def list_events(
    db: Session,
    *,
    starts_before: datetime | None = None,
    ends_after: datetime | None = None,
    job_id: str | None = None,
    candidate_id: str | None = None,
) -> list[RecruitmentEvent]:
    query = db.query(RecruitmentEvent)
    if starts_before is not None:
        query = query.filter(RecruitmentEvent.starts_at < starts_before)
    if ends_after is not None:
        query = query.filter(RecruitmentEvent.ends_at > ends_after)
    if job_id:
        query = query.filter(RecruitmentEvent.job_id == job_id)
    if candidate_id:
        query = query.filter(RecruitmentEvent.candidate_id == candidate_id)
    return query.order_by(RecruitmentEvent.starts_at.asc(), RecruitmentEvent.id.asc()).all()


def list_eligible_applications(db: Session):
    return (
        db.query(JobCandidate, Candidate, Job)
        .join(Candidate, Candidate.id == JobCandidate.candidate_id)
        .join(Job, Job.id == JobCandidate.job_id)
        .filter(
            JobCandidate.application_status.in_(
                ("SELECTED", "INTERVIEW", "OFFER", "HIRED")
            )
        )
        .order_by(Job.title.asc(), Candidate.name.asc(), JobCandidate.id.asc())
        .all()
    )
