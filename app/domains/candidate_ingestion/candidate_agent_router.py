"""Least-privilege HTTP API for provider adapters in ASIATI Candidate Agent."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.deps import get_db
from app.domains.candidate_ingestion import agent_source_service
from app.domains.candidate_ingestion.indeed_agent_auth import (
    AgentPrincipal,
    get_indeed_resume_agent_principal,
)

router = APIRouter(prefix="/api/agents/candidate-source", tags=["candidate-source-agent"])


class CandidateSourceResponse(BaseModel):
    event_id: str
    provider: str
    status: str
    existing: bool
    queued: bool


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, agent_source_service.CandidateSourceValidationError):
        return HTTPException(status_code=exc.status_code, detail=exc.code)
    return HTTPException(status_code=500, detail="Error interno del servidor.")


@router.post("/candidate", response_model=CandidateSourceResponse)
async def ingest_candidate(
    provider: str = Form(..., min_length=1, max_length=50),
    source_account: str = Form(..., min_length=1, max_length=200),
    external_id: str = Form(..., min_length=1, max_length=500),
    candidate_name: str = Form(..., min_length=1, max_length=1000),
    job_title: str | None = Form(default=None, max_length=1000),
    external_job_id: str | None = Form(default=None, max_length=500),
    location: str | None = Form(default=None, max_length=1000),
    applied_at: str | None = Form(default=None, max_length=200),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    principal: AgentPrincipal = Depends(get_indeed_resume_agent_principal),
):
    data = await file.read(agent_source_service.MAX_DOCUMENT_BYTES + 1)
    try:
        result = agent_source_service.ingest_candidate_document(
            db,
            owner_sub=principal.owner_sub,
            provider=provider,
            source_account=source_account,
            external_id=external_id,
            candidate_name=candidate_name,
            job_title=job_title,
            external_job_id=external_job_id,
            location=location,
            applied_at=applied_at,
            filename=file.filename,
            content_type=file.content_type or "",
            data=data,
        )
    except Exception as exc:
        db.rollback()
        raise _translate(exc)

    return CandidateSourceResponse(
        event_id=result.event_id,
        provider=result.provider,
        status=result.status,
        existing=result.existing,
        queued=result.queued,
    )
