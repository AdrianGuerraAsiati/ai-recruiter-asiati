"""Private, account-bound psychotechnical view for applicants and employees."""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_current_principal, get_db
from app.domains.psychotechnical import catalog, service
from app.domains.psychotechnical.models import PsychotechnicalAssignment
from app.models import JobCandidate

router = APIRouter(prefix="/api/psychotechnical/me", tags=["Own psychotechnical"])


def _profile_id(principal):
    profile_id = str((principal.get("profile") or {}).get("id") or "")
    if not profile_id:
        raise HTTPException(status_code=403, detail="Tu cuenta no tiene una ficha vinculada.")
    return profile_id


def _own_assignment(db: Session, profile_id: str, assignment_id: str):
    try:
        normalized_id = str(UUID(assignment_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Prueba no encontrada.") from exc
    return (
        db.query(PsychotechnicalAssignment)
        .join(
            JobCandidate,
            JobCandidate.candidate_id == PsychotechnicalAssignment.candidate_id,
        )
        .filter(
            PsychotechnicalAssignment.id == normalized_id,
            JobCandidate.employee_id == profile_id,
        )
        .first()
    )


@router.get("")
def own_assignments(
    db: Session = Depends(get_db),
    principal: dict = Depends(get_current_principal),
):
    profile_id = _profile_id(principal)
    # Backfill applicants created before automatic test allocation was enabled.
    # Always scope the lookup to the authenticated profile; never trust an
    # employee/candidate identifier supplied by the browser.
    applications = (
        db.query(JobCandidate)
        .filter(JobCandidate.employee_id == profile_id)
        .order_by(JobCandidate.id.asc())
        .all()
    )
    candidate_jobs = {}
    for application in applications:
        candidate_jobs.setdefault(str(application.candidate_id), str(application.job_id))
    for candidate_id, job_id in candidate_jobs.items():
        service.ensure_hiring_assignments(
            db,
            candidate_id=candidate_id,
            job_id=job_id,
            created_by_sub="system:psychotechnical-default",
        )

    rows = (
        db.query(PsychotechnicalAssignment)
        .filter(PsychotechnicalAssignment.candidate_id.in_(list(candidate_jobs)))
        .order_by(PsychotechnicalAssignment.created_at.desc())
        .all()
        if candidate_jobs else []
    )
    items = []
    for assignment in rows:
        test = catalog.require_test(assignment.test_key)
        items.append({
            "id": str(assignment.id),
            "test_name": test["name"],
            "test_description": test["description"],
            "status": service._status_for(assignment),
            "job_title": assignment.job.title if assignment.job else None,
            "expires_at": assignment.expires_at.isoformat(),
            "completed_at": assignment.completed_at.isoformat() if assignment.completed_at else None,
            "duration_minutes": test["duration_minutes"],
        })
    return {"items": items}


@router.post("/{assignment_id}/launch")
def launch_own_assignment(
    assignment_id: str,
    db: Session = Depends(get_db),
    principal: dict = Depends(get_current_principal),
):
    assignment = _own_assignment(db, _profile_id(principal), assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="Prueba no encontrada.")
    if service._status_for(assignment) not in ("PENDING", "IN_PROGRESS"):
        raise HTTPException(status_code=409, detail="Esta prueba ya no está disponible.")
    # Rotate the opaque bearer token without resetting IN_PROGRESS state or answers.
    token = service._public_token()
    assignment.token_hash = service._token_hash(token)
    db.commit()
    return {"token": token}
