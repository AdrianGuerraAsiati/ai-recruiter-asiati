"""Recruitment calendar schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


RecruitmentEventKind = Literal["PHONE_CALL", "ONSITE_INTERVIEW"]
RecruitmentEventStatus = Literal["SCHEDULED", "COMPLETED", "CANCELED"]


class RecruitmentEventCreate(BaseModel):
    job_id: str
    candidate_id: str
    kind: RecruitmentEventKind
    starts_at: datetime
    ends_at: datetime
    location: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=4000)


class RecruitmentEventUpdate(BaseModel):
    kind: RecruitmentEventKind | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    location: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=4000)
    status: RecruitmentEventStatus | None = None
