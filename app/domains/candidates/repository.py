"""Candidates repository."""

from datetime import datetime, timezone
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.candidates.exceptions import CandidateRetentionProtected
from app.models import (
    Candidate,
    CandidateRestrictionEvent,
    Evaluation,
    Job,
    JobCandidate,
    RankingItem,
)


def get_candidate(db: Session, candidate_id: str, owner_sub: str | None = None) -> Candidate | None:
    query = db.query(Candidate).filter(Candidate.id == candidate_id)
    if owner_sub is not None:
        query = query.filter(Candidate.owner_sub == owner_sub)
    return query.first()


def list_candidates(db: Session, owner_sub: str | None = None) -> list[Candidate]:
    query = db.query(Candidate)
    if owner_sub is not None:
        query = query.filter(Candidate.owner_sub == owner_sub)
    return query.order_by(Candidate.created_at.desc()).all()


def list_candidates_for_country(
    db: Session,
    *,
    country_code: str,
    owner_sub: str | None = None,
    include_banned: bool = False,
) -> list[Candidate]:
    """Return candidates with at least one application in the requested country."""
    normalized_country = str(country_code or "").strip().upper()
    if not normalized_country:
        return []

    country_assignment_exists = (
        db.query(JobCandidate.id)
        .join(Job, Job.id == JobCandidate.job_id)
        .filter(
            JobCandidate.candidate_id == Candidate.id,
            func.upper(Job.country_code) == normalized_country,
        )
        .exists()
    )
    query = db.query(Candidate).filter(
        or_(
            func.upper(Candidate.country_code) == normalized_country,
            country_assignment_exists,
        )
    )
    if owner_sub is not None:
        query = query.filter(Candidate.owner_sub == owner_sub)
    if not include_banned:
        query = query.filter(Candidate.is_banned.is_(False))
    return query.order_by(Candidate.created_at.desc(), Candidate.id.desc()).all()


def count_candidates_for_country(
    db: Session,
    *,
    country_code: str,
    owner_sub: str | None = None,
    include_banned: bool = False,
) -> int:
    normalized_country = str(country_code or "").strip().upper()
    if not normalized_country:
        return 0

    country_assignment_exists = (
        db.query(JobCandidate.id)
        .join(Job, Job.id == JobCandidate.job_id)
        .filter(
            JobCandidate.candidate_id == Candidate.id,
            func.upper(Job.country_code) == normalized_country,
        )
        .exists()
    )
    query = db.query(Candidate).filter(
        or_(
            func.upper(Candidate.country_code) == normalized_country,
            country_assignment_exists,
        )
    )
    if owner_sub is not None:
        query = query.filter(Candidate.owner_sub == owner_sub)
    if not include_banned:
        query = query.filter(Candidate.is_banned.is_(False))
    return int(query.count() or 0)


def list_candidates_page(
    db: Session,
    *,
    owner_sub: str | None = None,
    page: int = 1,
    page_size: int = 20,
    sort: str = "created_desc",
    country_code: str = "",
) -> tuple[list[Candidate], int]:
    """Return one stable candidate page and its total count."""
    query = db.query(Candidate)
    if owner_sub is not None:
        query = query.filter(Candidate.owner_sub == owner_sub)

    normalized_country = str(country_code or "").strip().upper()
    if normalized_country:
        country_assignment_exists = (
            db.query(JobCandidate.id)
            .join(Job, Job.id == JobCandidate.job_id)
            .filter(
                JobCandidate.candidate_id == Candidate.id,
                func.upper(Job.country_code) == normalized_country,
            )
            .exists()
        )
        query = query.filter(
            or_(
                func.upper(Candidate.country_code) == normalized_country,
                country_assignment_exists,
            )
        )

    total = query.count() or 0
    if sort == "name_asc":
        query = query.order_by(func.lower(Candidate.name).asc(), Candidate.id.asc())
    elif sort == "name_desc":
        query = query.order_by(func.lower(Candidate.name).desc(), Candidate.id.asc())
    else:
        query = query.order_by(Candidate.created_at.desc(), Candidate.id.desc())

    items = (
        query.offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total


def list_applications_page(
    db: Session,
    *,
    owner_sub: str | None = None,
    page: int = 1,
    page_size: int = 25,
    status: str = "",
    q: str = "",
):
    """Return job applications with candidate and vacancy context."""
    query = (
        db.query(JobCandidate, Candidate, Job)
        .join(Candidate, Candidate.id == JobCandidate.candidate_id)
        .join(Job, Job.id == JobCandidate.job_id)
    )
    if owner_sub is not None:
        query = query.filter(
            Candidate.owner_sub == owner_sub,
            Job.owner_sub == owner_sub,
        )

    normalized_status = str(status or "").strip().upper()
    if normalized_status:
        query = query.filter(JobCandidate.application_status == normalized_status)

    search = str(q or "").strip()
    if search:
        pattern = f"%{search}%"
        query = query.filter(
            or_(
                Candidate.name.ilike(pattern),
                Candidate.email.ilike(pattern),
                Job.title.ilike(pattern),
            )
        )

    total = int(query.count() or 0)
    rows = (
        query.order_by(
            JobCandidate.status_changed_at.desc(),
            JobCandidate.assigned_at.desc(),
            JobCandidate.id.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return rows, total


def count_candidates(
    db: Session,
    *,
    owner_sub: str | None = None,
    include_banned: bool = False,
) -> int:
    query = db.query(Candidate)
    if owner_sub is not None:
        query = query.filter(Candidate.owner_sub == owner_sub)
    if not include_banned:
        query = query.filter(Candidate.is_banned.is_(False))
    return int(query.count() or 0)


def count_candidates_for_job(
    db: Session,
    *,
    job_id: str,
    owner_sub: str | None = None,
    include_banned: bool = False,
) -> int:
    query = (
        db.query(Candidate)
        .join(JobCandidate, JobCandidate.candidate_id == Candidate.id)
        .filter(JobCandidate.job_id == job_id)
    )
    if owner_sub is not None:
        query = query.filter(Candidate.owner_sub == owner_sub)
    if not include_banned:
        query = query.filter(Candidate.is_banned.is_(False))
    return int(query.count() or 0)


def create_candidate(
    db: Session,
    *,
    name: str,
    email: str | None = None,
    metadata: dict | None = None,
    owner_sub: str | None = None,
) -> Candidate:
    candidate = Candidate(name=name, email=email, metadata_=metadata or {}, owner_sub=owner_sub)
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return candidate


def create_candidate_pending(
    db: Session,
    *,
    name: str,
    email: str | None = None,
    metadata: dict | None = None,
    owner_sub: str,
) -> Candidate:
    """Create a candidate inside the caller-owned transaction."""
    candidate = Candidate(
        name=name,
        email=email,
        metadata_=metadata or {},
        owner_sub=owner_sub,
    )
    db.add(candidate)
    db.flush()
    return candidate


def update_candidate_document_metadata(
    db: Session,
    candidate: Candidate,
    *,
    filename: str,
    email: str | None,
) -> Candidate:
    """Update document metadata without replacing a different known email."""
    metadata = dict(candidate.metadata_ or {})
    metadata["filename"] = filename
    candidate.metadata_ = metadata
    if not candidate.email and email:
        candidate.email = email
    db.flush()
    return candidate


def ensure_candidate_assigned_to_job(
    db: Session,
    *,
    job_id: str,
    candidate_id: str,
) -> JobCandidate:
    """Idempotently assign a candidate and persist reliable country context."""
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).one_or_none()
    job = db.query(Job).filter(Job.id == job_id).one_or_none()
    if candidate is not None and job is not None:
        candidate_country = str(candidate.country_code or "").strip().upper()
        job_country = str(job.country_code or "").strip().upper()
        if not candidate_country and job_country:
            candidate.country_code = job_country
            db.flush()

    existing = (
        db.query(JobCandidate)
        .filter(
            JobCandidate.job_id == job_id,
            JobCandidate.candidate_id == candidate_id,
        )
        .first()
    )
    if existing is not None:
        return existing
    link = JobCandidate(job_id=job_id, candidate_id=candidate_id)
    savepoint = db.begin_nested()
    try:
        db.add(link)
        db.flush()
        savepoint.commit()
        return link
    except IntegrityError:
        savepoint.rollback()
        existing = (
            db.query(JobCandidate)
            .filter(
                JobCandidate.job_id == job_id,
                JobCandidate.candidate_id == candidate_id,
            )
            .first()
        )
        if existing is not None:
            return existing
        raise


def get_job_candidate(
    db: Session,
    *,
    job_id: str,
    candidate_id: str,
    owner_sub: str | None = None,
) -> JobCandidate | None:
    query = (
        db.query(JobCandidate)
        .join(Candidate, Candidate.id == JobCandidate.candidate_id)
        .filter(
            JobCandidate.job_id == job_id,
            JobCandidate.candidate_id == candidate_id,
        )
    )
    if owner_sub is not None:
        query = query.filter(Candidate.owner_sub == owner_sub)
    return query.first()


def set_job_candidate_status(
    db: Session,
    link: JobCandidate,
    *,
    status: str,
    changed_at: datetime | None = None,
) -> JobCandidate:
    link.application_status = status
    link.status_changed_at = changed_at or datetime.now(timezone.utc)
    db.flush()
    return link


def delete_candidate(db: Session, candidate_id: str) -> bool:
    raise CandidateRetentionProtected(
        "Candidate hard-delete is disabled by retention policy."
    )


def delete_all_candidates(db: Session, owner_sub: str | None = None) -> tuple[int, int]:
    raise CandidateRetentionProtected(
        "Bulk candidate hard-delete is disabled by retention policy."
    )


def set_candidate_restriction(
    db: Session,
    candidate: Candidate,
    *,
    is_banned: bool,
    reason: str,
    created_by_sub: str,
) -> tuple[Candidate, CandidateRestrictionEvent | None, bool]:
    if bool(candidate.is_banned) == bool(is_banned):
        return candidate, None, False

    now = datetime.now(timezone.utc)
    candidate.is_banned = bool(is_banned)
    candidate.banned_at = now if is_banned else None
    candidate.banned_by_sub = created_by_sub if is_banned else None
    candidate.banned_reason = reason if is_banned else None

    event = CandidateRestrictionEvent(
        candidate_id=candidate.id,
        action="BANNED" if is_banned else "UNBANNED",
        reason=reason,
        created_by_sub=created_by_sub,
        created_at=now,
    )
    db.add(event)
    db.commit()
    db.refresh(candidate)
    db.refresh(event)
    return candidate, event, True


def list_candidate_restriction_events(
    db: Session,
    *,
    candidate_id: str,
) -> list[CandidateRestrictionEvent]:
    return (
        db.query(CandidateRestrictionEvent)
        .filter(CandidateRestrictionEvent.candidate_id == candidate_id)
        .order_by(
            CandidateRestrictionEvent.created_at.desc(),
            CandidateRestrictionEvent.id.desc(),
        )
        .all()
    )


def list_candidates_for_job(
    db: Session,
    job_id: str,
    *,
    page: int = 1,
    page_size: int = 10,
    owner_sub: str | None = None,
) -> tuple[list[Candidate], int]:
    query = db.query(Candidate).join(JobCandidate, JobCandidate.candidate_id == Candidate.id).filter(JobCandidate.job_id == job_id)
    if owner_sub is not None:
        query = query.filter(Candidate.owner_sub == owner_sub)
    query = query.order_by(Candidate.name)
    total = query.count() or 0
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return items, total


def list_job_candidate_links(
    db: Session,
    *,
    job_id: str,
    candidate_ids: list[str],
) -> dict[str, JobCandidate]:
    if not candidate_ids:
        return {}
    links = (
        db.query(JobCandidate)
        .filter(
            JobCandidate.job_id == job_id,
            JobCandidate.candidate_id.in_(candidate_ids),
        )
        .all()
    )
    return {link.candidate_id: link for link in links}


def assign_candidates_to_job(
    db: Session,
    job_id: str,
    candidate_ids: list[str],
    owner_sub: str | None = None,
) -> tuple[int, int]:
    assigned = 0
    skipped = 0

    candidate_query = db.query(Candidate.id).filter(Candidate.id.in_(candidate_ids))
    if owner_sub is not None:
        candidate_query = candidate_query.filter(Candidate.owner_sub == owner_sub)

    candidate_query = candidate_query.filter(Candidate.is_banned.is_(False))
    allowed_ids = {candidate_id for (candidate_id,) in candidate_query.all()}

    for cid in candidate_ids:
        if cid not in allowed_ids:
            skipped += 1
            continue

        existing = db.query(JobCandidate).filter(JobCandidate.job_id == job_id, JobCandidate.candidate_id == cid).first()
        if existing:
            skipped += 1
            continue

        savepoint = db.begin_nested()
        try:
            db.add(JobCandidate(job_id=job_id, candidate_id=cid))
            db.flush()
            savepoint.commit()
            assigned += 1
        except IntegrityError:
            savepoint.rollback()
            skipped += 1

    db.commit()
    return assigned, skipped
