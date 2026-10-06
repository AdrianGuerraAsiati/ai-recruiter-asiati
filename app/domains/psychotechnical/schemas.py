"""API schemas for psychotechnical assessments."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CreatePsychotechnicalAssignmentRequest(BaseModel):
    candidate_id: str
    job_id: str | None = None
    expires_days: int = Field(default=7, ge=1, le=30)


class RegeneratePsychotechnicalLinkRequest(BaseModel):
    expires_days: int = Field(default=7, ge=1, le=30)


class PsychotechnicalAnswer(BaseModel):
    question_id: str = Field(min_length=1, max_length=16)
    option_id: str = Field(min_length=1, max_length=8)


class SubmitPsychotechnicalRequest(BaseModel):
    answers: list[PsychotechnicalAnswer] = Field(min_length=1, max_length=40)
