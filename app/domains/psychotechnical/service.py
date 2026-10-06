"""Business logic for objective psychotechnical assessments."""

from __future__ import annotations

import hashlib
import secrets
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.domains.psychotechnical import catalog
from app.domains.psychotechnical.models import PsychotechnicalAssignment
from app.models import Candidate, Job


class PsychotechnicalNotFound(LookupError):
    pass


class PsychotechnicalConflict(RuntimeError):
    pass


class PsychotechnicalExpired(RuntimeError):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _is_expired(assignment: PsychotechnicalAssignment) -> bool:
    return _as_utc(assignment.expires_at) <= _utcnow()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _public_token() -> str:
    return secrets.token_urlsafe(32)


def _status_for(assignment: PsychotechnicalAssignment) -> str:
    if assignment.status in {"COMPLETED", "CANCELED"}:
        return assignment.status
    if _is_expired(assignment):
        return "EXPIRED"
    return assignment.status


def _assignment_payload(assignment: PsychotechnicalAssignment) -> dict:
    return {
        "id": assignment.id,
        "candidate_id": assignment.candidate_id,
        "candidate_name": assignment.candidate.name if assignment.candidate else None,
        "candidate_email": assignment.candidate.email if assignment.candidate else None,
        "job_id": assignment.job_id,
        "job_title": assignment.job.title if assignment.job else None,
        "test_key": assignment.test_key,
        "test_name": catalog.TEST_NAME,
        "test_version": assignment.test_version,
        "status": _status_for(assignment),
        "expires_at": assignment.expires_at.isoformat(),
        "started_at": assignment.started_at.isoformat() if assignment.started_at else None,
        "completed_at": assignment.completed_at.isoformat() if assignment.completed_at else None,
        "duration_seconds": assignment.duration_seconds,
        "score_total": assignment.score_total,
        "dimension_scores": assignment.dimension_scores or {},
        "created_at": assignment.created_at.isoformat(),
    }


def create_assignment(
    db: Session,
    *,
    candidate_id: str,
    job_id: str | None,
    expires_days: int,
    created_by_sub: str,
) -> tuple[PsychotechnicalAssignment, str]:
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).one_or_none()
    if candidate is None:
        raise PsychotechnicalNotFound("candidate")
    if bool(candidate.is_banned):
        raise PsychotechnicalConflict(
            "No se puede asignar una prueba a un candidato vetado."
        )

    job = None
    if job_id:
        job = db.query(Job).filter(Job.id == job_id).one_or_none()
        if job is None:
            raise PsychotechnicalNotFound("job")
    existing = (
        db.query(PsychotechnicalAssignment)
        .filter(
            PsychotechnicalAssignment.candidate_id == candidate_id,
            PsychotechnicalAssignment.test_key == catalog.TEST_KEY,
            PsychotechnicalAssignment.status.in_(("PENDING", "IN_PROGRESS")),
        )
        .order_by(PsychotechnicalAssignment.created_at.desc())
        .first()
    )
    if existing is not None and not _is_expired(existing):
        raise PsychotechnicalConflict(
            "El candidato ya tiene una prueba psicotécnica pendiente o en curso."
        )

    token = _public_token()
    assignment = PsychotechnicalAssignment(
        candidate_id=candidate_id,
        job_id=job.id if job else None,
        test_key=catalog.TEST_KEY,
        test_version=catalog.TEST_VERSION,
        token_hash=_token_hash(token),
        status="PENDING",
        expires_at=_utcnow() + timedelta(days=expires_days),
        created_by_sub=created_by_sub,
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment, token


def list_assignments(
    db: Session,
    *,
    status: str | None = None,
    q: str = "",
    candidate_id: str | None = None,
) -> list[dict]:
    query = db.query(PsychotechnicalAssignment)
    if candidate_id:
        query = query.filter(PsychotechnicalAssignment.candidate_id == candidate_id)
    if status:
        if status == "EXPIRED":
            query = query.filter(
                PsychotechnicalAssignment.status.in_(("PENDING", "IN_PROGRESS")),
                PsychotechnicalAssignment.expires_at <= _utcnow(),
            )
        else:
            query = query.filter(PsychotechnicalAssignment.status == status)
    normalized = q.strip()
    if normalized:
        pattern = f"%{normalized}%"
        query = query.join(Candidate).filter(
            or_(Candidate.name.ilike(pattern), Candidate.email.ilike(pattern))
        )
    rows = query.order_by(PsychotechnicalAssignment.created_at.desc()).all()
    return [_assignment_payload(row) for row in rows]


def _assignment_by_token(db: Session, token: str) -> PsychotechnicalAssignment:
    assignment = (
        db.query(PsychotechnicalAssignment)
        .filter(PsychotechnicalAssignment.token_hash == _token_hash(token))
        .one_or_none()
    )
    if assignment is None:
        raise PsychotechnicalNotFound("assignment")
    if assignment.status == "CANCELED":
        raise PsychotechnicalConflict("La prueba fue cancelada.")
    if assignment.status != "COMPLETED" and _is_expired(assignment):
        raise PsychotechnicalExpired("La prueba expiró.")
    return assignment


def public_assignment(db: Session, token: str) -> dict:
    assignment = _assignment_by_token(db, token)
    return {
        "status": _status_for(assignment),
        "candidate_name": assignment.candidate.name if assignment.candidate else None,
        "job_title": assignment.job.title if assignment.job else None,
        "test_name": catalog.TEST_NAME,
        "test_description": catalog.TEST_DESCRIPTION,
        "duration_minutes": catalog.DURATION_MINUTES,
        "question_count": len(catalog.QUESTIONS),
        "dimensions": list(catalog.DIMENSION_LABELS.values()),
        "expires_at": assignment.expires_at.isoformat(),
    }


def start_assignment(db: Session, token: str) -> dict:
    assignment = _assignment_by_token(db, token)
    if assignment.status == "COMPLETED":
        raise PsychotechnicalConflict("La prueba ya fue completada.")
    if assignment.status == "PENDING":
        assignment.status = "IN_PROGRESS"
        assignment.started_at = _utcnow()
        db.commit()
        db.refresh(assignment)
    return {
        "assignment": public_assignment(db, token),
        "questions": catalog.public_questions(),
    }


def submit_assignment(db: Session, token: str, answers: list[dict]) -> dict:
    assignment = _assignment_by_token(db, token)
    if assignment.status == "COMPLETED":
        raise PsychotechnicalConflict("La prueba ya fue completada.")
    if assignment.status == "PENDING":
        assignment.status = "IN_PROGRESS"
        assignment.started_at = _utcnow()

    provided = {item["question_id"]: item["option_id"] for item in answers}
    expected_ids = {item["id"] for item in catalog.QUESTIONS}
    if len(answers) != len(expected_ids) or set(provided) != expected_ids:
        raise PsychotechnicalConflict("Debes responder todas las preguntas una sola vez.")

    dimension_correct: dict[str, int] = defaultdict(int)
    dimension_total: dict[str, int] = defaultdict(int)
    normalized_answers = []

    for question in catalog.QUESTIONS:
        selected = provided[question["id"]]
        valid_options = {option["id"] for option in question["options"]}
        if selected not in valid_options:
            raise PsychotechnicalConflict("Una respuesta contiene una opción inválida.")

        correct = selected == question["correct"]
        dimension = question["dimension"]
        dimension_total[dimension] += 1
        if correct:
            dimension_correct[dimension] += 1
        normalized_answers.append(
            {
                "question_id": question["id"],
                "option_id": selected,
                "correct": correct,
            }
        )

    total_correct = sum(1 for item in normalized_answers if item["correct"])
    total_questions = len(catalog.QUESTIONS)
    score_total = round((total_correct / total_questions) * 100)

    dimension_scores = {
        dimension: {
            "label": catalog.DIMENSION_LABELS[dimension],
            "score": round((dimension_correct[dimension] / total) * 100),
            "correct": dimension_correct[dimension],
            "total": total,
        }
        for dimension, total in dimension_total.items()
    }

    completed_at = _utcnow()
    started_at = _as_utc(assignment.started_at) if assignment.started_at else completed_at
    assignment.status = "COMPLETED"
    assignment.completed_at = completed_at
    assignment.duration_seconds = max(
        0,
        int((completed_at - started_at).total_seconds()),
    )
    assignment.answers = normalized_answers
    assignment.score_total = score_total
    assignment.dimension_scores = dimension_scores
    db.commit()
    db.refresh(assignment)

    return {
        "status": "COMPLETED",
        "message": (
            "Respuestas enviadas correctamente. El equipo de Talento Humano revisará "
            "el resultado junto con el resto del proceso."
        ),
    }


def regenerate_link(
    db: Session,
    assignment_id: str,
    *,
    expires_days: int,
) -> tuple[PsychotechnicalAssignment, str]:
    assignment = (
        db.query(PsychotechnicalAssignment)
        .filter(PsychotechnicalAssignment.id == assignment_id)
        .one_or_none()
    )
    if assignment is None:
        raise PsychotechnicalNotFound("assignment")
    if assignment.status in {"COMPLETED", "CANCELED"}:
        raise PsychotechnicalConflict(
            "Solo se puede generar un nuevo enlace para pruebas pendientes o en curso."
        )

    token = _public_token()
    assignment.token_hash = _token_hash(token)
    assignment.status = "PENDING"
    assignment.expires_at = _utcnow() + timedelta(days=expires_days)
    assignment.started_at = None
    assignment.completed_at = None
    assignment.duration_seconds = None
    assignment.answers = None
    assignment.score_total = None
    assignment.dimension_scores = None
    db.commit()
    db.refresh(assignment)
    return assignment, token


def cancel_assignment(db: Session, assignment_id: str) -> dict:
    assignment = (
        db.query(PsychotechnicalAssignment)
        .filter(PsychotechnicalAssignment.id == assignment_id)
        .one_or_none()
    )
    if assignment is None:
        raise PsychotechnicalNotFound("assignment")
    if assignment.status == "COMPLETED":
        raise PsychotechnicalConflict("No se puede cancelar una prueba ya completada.")
    assignment.status = "CANCELED"
    db.commit()
    db.refresh(assignment)
    return _assignment_payload(assignment)
