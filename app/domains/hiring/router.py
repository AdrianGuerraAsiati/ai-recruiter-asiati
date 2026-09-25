"""Candidate hiring HTTP routes."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_db, require_permission
from app.domains.candidates.exceptions import (
    CandidateNotFound,
    JobCandidateNotFound,
    JobNotFound,
)
from app.domains.employees import service as employees_service
from app.domains.hiring import service
from app.domains.hiring.schemas import HireCandidateRequest
from app.domains.training import service as training_service


router = APIRouter(prefix="/api/jobs", tags=["hiring"])


def _translate(exc: Exception):
    if isinstance(exc, JobNotFound):
        raise HTTPException(status_code=404, detail="Vacante no encontrada.")
    if isinstance(exc, (CandidateNotFound, JobCandidateNotFound)):
        raise HTTPException(
            status_code=404,
            detail="Candidato no encontrado en esta vacante.",
        )
    if isinstance(exc, service.HiringValidationError):
        raise HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, service.HiringConflictError):
        raise HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, employees_service.EmployeeAlreadyExists):
        raise HTTPException(
            status_code=409,
            detail="Ya existe un usuario con este correo.",
        )
    if isinstance(
        exc,
        (
            employees_service.EmployeeIdentityError,
            employees_service.EmployeeProvisioningError,
        ),
    ):
        raise HTTPException(
            status_code=502,
            detail="No fue posible crear el acceso del empleado.",
        )
    if isinstance(exc, training_service.TrainingAssignmentError):
        raise HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, training_service.TrainingStateError):
        raise HTTPException(status_code=422, detail=str(exc))
    raise exc


@router.post("/{job_id}/candidates/{candidate_id}/hire")
def hire_candidate(
    job_id: str,
    candidate_id: str,
    body: HireCandidateRequest,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_permission("employees.create")),
):
    try:
        return service.hire_candidate(
            db,
            owner_sub=principal["sub"],
            job_id=job_id,
            candidate_id=candidate_id,
            created_by_sub=principal["sub"],
            email=body.email,
            first_name=body.first_name,
            last_name=body.last_name,
            job_title=body.job_title,
            department=body.department,
            hire_date=body.hire_date,
        )
    except Exception as exc:
        _translate(exc)
