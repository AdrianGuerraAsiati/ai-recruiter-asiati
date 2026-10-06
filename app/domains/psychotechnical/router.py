"""Routes for objective psychotechnical assessments."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.deps import get_db, require_permission
from app.domains.psychotechnical import service
from app.domains.psychotechnical.schemas import (
    CreatePsychotechnicalAssignmentRequest,
    RegeneratePsychotechnicalLinkRequest,
    SubmitPsychotechnicalRequest,
)


router = APIRouter(prefix="/api/psychotechnical", tags=["Psychotechnical"])
public_router = APIRouter(prefix="/api/public/psychotechnical", tags=["Psychotechnical public"])


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, service.PsychotechnicalNotFound):
        return HTTPException(status_code=404, detail="Prueba o candidato no encontrado.")
    if isinstance(exc, service.PsychotechnicalExpired):
        return HTTPException(status_code=410, detail=str(exc))
    if isinstance(exc, service.PsychotechnicalConflict):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=500, detail="No fue posible procesar la prueba psicotécnica.")


@router.get("/assignments")
def get_assignments(
    status: str | None = Query(default=None),
    q: str = Query(default="", max_length=120),
    candidate_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("psychotechnical.read")),
):
    return {
        "items": service.list_assignments(
            db,
            status=status,
            q=q,
            candidate_id=candidate_id,
        )
    }


@router.post("/assignments")
def create_assignment(
    body: CreatePsychotechnicalAssignmentRequest,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_permission("psychotechnical.manage")),
):
    try:
        assignment, token = service.create_assignment(
            db,
            candidate_id=body.candidate_id,
            job_id=body.job_id,
            expires_days=body.expires_days,
            created_by_sub=principal["sub"],
        )
    except Exception as exc:
        raise _translate(exc) from exc

    return {
        "assignment": service.list_assignments(
            db,
            candidate_id=assignment.candidate_id,
        )[0],
        "token": token,
    }


@router.post("/assignments/{assignment_id}/link")
def regenerate_assignment_link(
    assignment_id: str,
    body: RegeneratePsychotechnicalLinkRequest,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("psychotechnical.manage")),
):
    try:
        assignment, token = service.regenerate_link(
            db,
            assignment_id,
            expires_days=body.expires_days,
        )
    except Exception as exc:
        raise _translate(exc) from exc
    return {
        "assignment_id": assignment.id,
        "token": token,
        "expires_at": assignment.expires_at.isoformat(),
    }


@router.post("/assignments/{assignment_id}/cancel")
def cancel_assignment(
    assignment_id: str,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("psychotechnical.manage")),
):
    try:
        return service.cancel_assignment(db, assignment_id)
    except Exception as exc:
        raise _translate(exc) from exc


@public_router.get("/{token}")
def public_assignment(
    token: str,
    db: Session = Depends(get_db),
):
    try:
        return service.public_assignment(db, token)
    except Exception as exc:
        raise _translate(exc) from exc


@public_router.post("/{token}/start")
def start_public_assignment(
    token: str,
    db: Session = Depends(get_db),
):
    try:
        return service.start_assignment(db, token)
    except Exception as exc:
        raise _translate(exc) from exc


@public_router.post("/{token}/submit")
def submit_public_assignment(
    token: str,
    body: SubmitPsychotechnicalRequest,
    db: Session = Depends(get_db),
):
    try:
        return service.submit_assignment(
            db,
            token,
            [answer.model_dump() for answer in body.answers],
        )
    except Exception as exc:
        raise _translate(exc) from exc
