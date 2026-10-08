"""Business logic for ASIATI psychotechnical assessments."""

from __future__ import annotations

import hashlib
import secrets
from collections import Counter, defaultdict
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


def _test_definition(test_key: str) -> dict:
    try:
        return catalog.require_test(test_key)
    except KeyError as exc:
        raise PsychotechnicalConflict("La prueba seleccionada no existe.") from exc


def _assignment_payload(assignment: PsychotechnicalAssignment) -> dict:
    test = _test_definition(assignment.test_key)
    return {
        "id": assignment.id,
        "candidate_id": assignment.candidate_id,
        "candidate_name": assignment.candidate.name if assignment.candidate else None,
        "candidate_email": assignment.candidate.email if assignment.candidate else None,
        "job_id": assignment.job_id,
        "job_title": assignment.job.title if assignment.job else None,
        "test_key": assignment.test_key,
        "test_name": test["name"],
        "test_code": test["code"],
        "source_version": test["source_version"],
        "test_kind": test["kind"],
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
    test_key: str,
    expires_days: int,
    created_by_sub: str,
) -> tuple[PsychotechnicalAssignment, str]:
    test = _test_definition(test_key)

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
            PsychotechnicalAssignment.test_key == test["key"],
            PsychotechnicalAssignment.status.in_(("PENDING", "IN_PROGRESS")),
        )
        .order_by(PsychotechnicalAssignment.created_at.desc())
        .first()
    )
    if existing is not None and not _is_expired(existing):
        raise PsychotechnicalConflict(
            f"El candidato ya tiene una prueba {test['name']} pendiente o en curso."
        )

    token = _public_token()
    assignment = PsychotechnicalAssignment(
        candidate_id=candidate_id,
        job_id=job.id if job else None,
        test_key=test["key"],
        test_version=1,
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
    test_key: str | None = None,
) -> list[dict]:
    query = db.query(PsychotechnicalAssignment)
    if candidate_id:
        query = query.filter(PsychotechnicalAssignment.candidate_id == candidate_id)
    if test_key:
        query = query.filter(PsychotechnicalAssignment.test_key == test_key)
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
    test = _test_definition(assignment.test_key)
    payload = {
        "status": _status_for(assignment),
        "candidate_name": assignment.candidate.name if assignment.candidate else None,
        "job_title": assignment.job.title if assignment.job else None,
        "test_key": test["key"],
        "test_name": test["name"],
        "test_code": test["code"],
        "source_version": test["source_version"],
        "test_kind": test["kind"],
        "test_description": test["description"],
        "duration_minutes": test["duration_minutes"],
        "question_count": test["question_count"],
        "expires_at": assignment.expires_at.isoformat(),
    }
    if "duration_seconds" in test:
        payload["duration_seconds"] = test["duration_seconds"]
    return payload


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
        "questions": catalog.public_questions(assignment.test_key),
    }


def _answer_map(answers: list[dict]) -> dict[str, str]:
    if len({item["question_id"] for item in answers}) != len(answers):
        raise PsychotechnicalConflict("No puedes enviar una pregunta más de una vez.")
    return {
        str(item["question_id"]): str(item["option_id"])
        for item in answers
    }


def _validate_full_answers(test: dict, answers: list[dict]) -> dict[str, str]:
    provided = _answer_map(answers)
    expected_ids = {item["id"] for item in test["questions"]}
    if len(provided) != len(expected_ids) or set(provided) != expected_ids:
        raise PsychotechnicalConflict("Debes responder todas las preguntas una sola vez.")
    return provided


def _validate_option(question: dict, selected: str) -> None:
    valid = {str(option["id"]) for option in question["options"]}
    if selected not in valid:
        raise PsychotechnicalConflict("Una respuesta contiene una opción inválida.")


def _score_common_sense(test: dict, answers: list[dict]) -> tuple[int, dict, list[dict]]:
    provided = _validate_full_answers(test, answers)
    normalized = []
    correct = 0
    for question in test["questions"]:
        selected = provided[question["id"]]
        _validate_option(question, selected)
        is_correct = selected == question["correct"]
        correct += int(is_correct)
        normalized.append(
            {
                "question_id": question["id"],
                "option_id": selected,
                "correct": is_correct,
            }
        )

    if correct >= 9:
        band = "Excelente criterio organizacional y responsabilidad"
    elif correct >= 7:
        band = "Buen criterio; requiere acompañamiento estratégico ocasional"
    elif correct >= 5:
        band = "Criterio básico; requiere supervisión frecuente"
    else:
        band = "Resultado bajo en criterio organizacional"

    score = round((correct / len(test["questions"])) * 100)
    result = {
        "RESULT": {
            "label": "Sentido común organizacional",
            "score": score,
            "correct": correct,
            "total": len(test["questions"]),
            "band": band,
        }
    }
    return score, result, normalized


TEMPERAMENT_LABELS = {
    "A": {
        "label": "Colérico",
        "competencies": ["Liderazgo", "Decisión", "Competitividad"],
        "description": "Orientación a resultados, decisión y acción directa.",
    },
    "B": {
        "label": "Flemático",
        "competencies": ["Adaptabilidad", "Cooperación", "Estabilidad"],
        "description": "Estabilidad, cooperación y preferencia por entornos colaborativos.",
    },
    "C": {
        "label": "Melancólico",
        "competencies": ["Análisis", "Precisión", "Planificación"],
        "description": "Análisis, estructura, precisión y planificación.",
    },
    "D": {
        "label": "Sanguíneo",
        "competencies": ["Expresividad", "Carisma", "Empatía"],
        "description": "Expresividad, interacción social y comunicación interpersonal.",
    },
}


def _score_temperament(test: dict, answers: list[dict]) -> tuple[None, dict, list[dict]]:
    provided = _validate_full_answers(test, answers)
    counts = Counter()
    normalized = []
    for question in test["questions"]:
        selected = provided[question["id"]]
        _validate_option(question, selected)
        counts[selected] += 1
        normalized.append(
            {
                "question_id": question["id"],
                "option_id": selected,
            }
        )

    maximum = max(counts.values(), default=0)
    primary = [
        key
        for key in ("A", "B", "C", "D")
        if counts.get(key, 0) == maximum
    ]
    result = {}
    total = len(test["questions"])
    for key in ("A", "B", "C", "D"):
        metadata = TEMPERAMENT_LABELS[key]
        count = counts.get(key, 0)
        result[key] = {
            **metadata,
            "count": count,
            "total": total,
            "score": round((count / total) * 100),
            "primary": key in primary,
        }
    result["PROFILE"] = {
        "label": "Perfil predominante",
        "profiles": [TEMPERAMENT_LABELS[key]["label"] for key in primary],
        "note": (
            "Resultado descriptivo. No se utiliza automáticamente para decidir "
            "idoneidad, descarte o ranking de candidatos."
        ),
    }
    return None, result, normalized


VALANTI_DIMENSIONS = {
    "TRUTH": {
        "label": "Verdad",
        "mean": 15.64794520547945,
        "sd": 4.703342348004798,
        "reference": 65.0,
    },
    "RECTITUDE": {
        "label": "Rectitud",
        "mean": 21.05068493150685,
        "sd": 4.444926618525877,
        "reference": 65.0,
        "factor": 843 / 545,
    },
    "PEACE": {
        "label": "Paz",
        "mean": 17.35342465753425,
        "sd": 6.60888710785178,
        "reference": 50.0,
    },
    "LOVE": {
        "label": "Amor",
        "mean": 16.68219178082192,
        "sd": 5.412005717762647,
        "reference": 65.0,
    },
    "NON_VIOLENCE": {
        "label": "No violencia",
        "mean": 21.22465753424657,
        "sd": 7.194262704638464,
        "reference": 65.0,
    },
}

# Mapping reconstructed from the formulas in RESULTADO - PRUEBA VALANTI.xlsx.
# Each tuple is (left-side dimension, right-side dimension).
VALANTI_SIDE_MAP = {
    1: ("LOVE", "RECTITUDE"),
    2: ("LOVE", "RECTITUDE"),
    3: ("TRUTH", "PEACE"),
    4: ("PEACE", "NON_VIOLENCE"),
    5: ("TRUTH", "RECTITUDE"),
    6: ("TRUTH", "RECTITUDE"),
    7: ("RECTITUDE", "TRUTH"),
    8: ("LOVE", "TRUTH"),
    9: ("NON_VIOLENCE", "TRUTH"),
    10: ("NON_VIOLENCE", "PEACE"),
    11: ("RECTITUDE", "NON_VIOLENCE"),
    12: ("TRUTH", "PEACE"),
    13: ("NON_VIOLENCE", "RECTITUDE"),
    14: ("NON_VIOLENCE", "PEACE"),
    15: ("NON_VIOLENCE", "LOVE"),
    16: ("TRUTH", "LOVE"),
    17: ("LOVE", "PEACE"),
    18: ("NON_VIOLENCE", "TRUTH"),
    19: ("PEACE", "LOVE"),
    20: ("TRUTH", "NON_VIOLENCE"),
    21: ("RECTITUDE", "PEACE"),
    22: ("NON_VIOLENCE", "LOVE"),
    23: ("NON_VIOLENCE", "TRUTH"),
    24: ("PEACE", "RECTITUDE"),
    25: ("PEACE", "TRUTH"),
    26: ("RECTITUDE", "PEACE"),
    27: ("NON_VIOLENCE", "LOVE"),
    28: ("RECTITUDE", "PEACE"),
    29: ("RECTITUDE", "NON_VIOLENCE"),
    30: ("NON_VIOLENCE", "LOVE"),
}


def _valanti_band(score: float) -> str:
    if score >= 74:
        return "Muy alto"
    if score >= 64:
        return "Alto"
    if score >= 54:
        return "Promedio alto"
    if score >= 44:
        return "Promedio"
    if score >= 34:
        return "Promedio bajo"
    if score >= 24:
        return "Bajo"
    return "Muy bajo"


def _score_valanti(test: dict, answers: list[dict]) -> tuple[None, dict, list[dict]]:
    provided = _validate_full_answers(test, answers)
    direct = defaultdict(float)
    normalized = []

    for index, question in enumerate(test["questions"], start=1):
        selected = provided[question["id"]]
        _validate_option(question, selected)
        try:
            left_points, right_points = [int(value) for value in selected.split("-", 1)]
        except (TypeError, ValueError) as exc:
            raise PsychotechnicalConflict("Distribución VALANTI inválida.") from exc
        if left_points + right_points != 3:
            raise PsychotechnicalConflict("Cada par VALANTI debe sumar tres puntos.")

        left_dimension, right_dimension = VALANTI_SIDE_MAP[index]
        direct[left_dimension] += left_points
        direct[right_dimension] += right_points
        normalized.append(
            {
                "question_id": question["id"],
                "option_id": selected,
                "left_points": left_points,
                "right_points": right_points,
            }
        )

    result = {}
    for key, metadata in VALANTI_DIMENSIONS.items():
        standard = ((direct[key] - metadata["mean"]) / metadata["sd"]) * 10 + 50
        standard *= metadata.get("factor", 1.0)
        result[key] = {
            "label": metadata["label"],
            "direct": round(direct[key], 2),
            "score": round(standard, 2),
            "band": _valanti_band(standard),
            "reference": metadata["reference"],
            "difference": round(standard - metadata["reference"], 2),
        }

    highest = max(
        (value for key, value in result.items()),
        key=lambda item: item["score"],
    )
    lowest = min(
        (value for key, value in result.items()),
        key=lambda item: item["score"],
    )
    result["PROFILE"] = {
        "label": "Lectura de valores",
        "highest": highest["label"],
        "lowest": lowest["label"],
        "note": (
            "La referencia ASIATI se muestra como contexto del archivo de resultados "
            "suministrado; no genera automáticamente una decisión de selección."
        ),
    }
    return None, result, normalized


ATTENTION_SECTION_LABELS = {
    "ALPHANUMERIC": "Alfanumérico",
    "LETTERS": "Letras",
    "FIGURES": "Figuras · versión digital",
}


def _score_attention(test: dict, answers: list[dict]) -> tuple[int, dict, list[dict]]:
    provided = _answer_map(answers)
    expected = {question["id"]: question for question in test["questions"]}
    if not set(provided).issubset(expected):
        raise PsychotechnicalConflict("La prueba contiene una pregunta inválida.")

    section_total = Counter()
    section_answered = Counter()
    section_correct = Counter()
    normalized = []

    for question in test["questions"]:
        section = question["section"]
        section_total[section] += 1
        selected = provided.get(question["id"])
        if selected is None:
            continue
        _validate_option(question, selected)
        is_correct = selected == question["correct"]
        section_answered[section] += 1
        section_correct[section] += int(is_correct)
        normalized.append(
            {
                "question_id": question["id"],
                "option_id": selected,
                "correct": is_correct,
                "section": section,
            }
        )

    result = {}
    section_scores = []
    for section in ("ALPHANUMERIC", "LETTERS", "FIGURES"):
        total = section_total[section]
        efficiency = section_answered[section] / total if total else 0
        efficacy = section_correct[section] / total if total else 0
        section_score = ((efficiency + efficacy) / 2) * 100
        section_scores.append(section_score)
        result[section] = {
            "label": ATTENTION_SECTION_LABELS[section],
            "score": round(section_score, 2),
            "answered": section_answered[section],
            "correct": section_correct[section],
            "total": total,
            "efficiency": round(efficiency * 100, 2),
            "efficacy": round(efficacy * 100, 2),
        }

    final = sum(section_scores) / len(section_scores)
    if final >= 85:
        band = "Nivel alto"
    elif final >= 75:
        band = "Nivel medio"
    else:
        band = "Nivel bajo"

    result["RESULT"] = {
        "label": "Calificación final",
        "score": round(final, 2),
        "band": band,
        "method": "Promedio de eficiencia y eficacia por cada una de las tres tareas.",
        "note": (
            "La tarea de figuras fue adaptada a pantalla para esta versión digital. "
            "Debe validarse internamente antes de equiparar sus resultados históricos "
            "con la versión impresa."
        ),
    }
    return round(final), result, normalized


def _score_assignment(
    test: dict,
    answers: list[dict],
) -> tuple[int | None, dict, list[dict]]:
    if test["key"] == catalog.COMMON_SENSE:
        return _score_common_sense(test, answers)
    if test["key"] == catalog.TEMPERAMENT:
        return _score_temperament(test, answers)
    if test["key"] == catalog.VALANTI:
        return _score_valanti(test, answers)
    if test["key"] == catalog.ATTENTION:
        return _score_attention(test, answers)
    raise PsychotechnicalConflict("La prueba seleccionada no tiene motor de calificación.")


def submit_assignment(db: Session, token: str, answers: list[dict]) -> dict:
    assignment = _assignment_by_token(db, token)
    if assignment.status == "COMPLETED":
        raise PsychotechnicalConflict("La prueba ya fue completada.")
    if assignment.status == "PENDING":
        assignment.status = "IN_PROGRESS"
        assignment.started_at = _utcnow()

    test = _test_definition(assignment.test_key)
    score_total, result, normalized_answers = _score_assignment(test, answers)

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
    assignment.dimension_scores = result
    db.commit()
    db.refresh(assignment)

    return {
        "status": "COMPLETED",
        "message": (
            "Respuestas enviadas correctamente. El equipo de Talento Humano revisará "
            "el resultado junto con las demás etapas del proceso."
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
