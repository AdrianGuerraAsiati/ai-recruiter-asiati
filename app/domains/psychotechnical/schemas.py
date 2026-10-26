"""API schemas for psychotechnical assessments."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CreatePsychotechnicalAssignmentRequest(BaseModel):
    candidate_id: str
    job_id: str | None = None
    test_key: str = Field(min_length=1, max_length=80)
    expires_days: int = Field(default=7, ge=1, le=30)


class RegeneratePsychotechnicalLinkRequest(BaseModel):
    expires_days: int = Field(default=7, ge=1, le=30)


class PsychotechnicalAnswer(BaseModel):
    question_id: str = Field(min_length=1, max_length=16)
    option_id: str = Field(min_length=1, max_length=8)


class SubmitPsychotechnicalRequest(BaseModel):
    # Attention tests legitimately permit zero answers at the official timeout.
    # All other tests enforce their completeness in the domain scorer.
    answers: list[PsychotechnicalAnswer] = Field(min_length=0, max_length=80)
