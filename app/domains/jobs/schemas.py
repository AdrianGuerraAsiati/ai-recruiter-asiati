"""Jobs schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


MAX_JOB_TITLE_CHARS = 200
MAX_JOB_DESCRIPTION_CHARS = 20_000
MAX_PROFILE_ITEMS = 100
MAX_PROFILE_ITEM_CHARS = 1_000


class EvaluationProfile(BaseModel):
    """Recruiter-reviewed structured criteria used for candidate evaluation."""

    model_config = ConfigDict(extra="forbid")

    required_technologies: list[str] = Field(default_factory=list, max_length=MAX_PROFILE_ITEMS)
    preferred_technologies: list[str] = Field(default_factory=list, max_length=MAX_PROFILE_ITEMS)
    required_certifications: list[str] = Field(default_factory=list, max_length=MAX_PROFILE_ITEMS)
    preferred_certifications: list[str] = Field(default_factory=list, max_length=MAX_PROFILE_ITEMS)
    minimum_years_experience: float | None = Field(default=None, ge=0)
    specific_experience: list[str] = Field(default_factory=list, max_length=MAX_PROFILE_ITEMS)
    responsibilities: list[str] = Field(default_factory=list, max_length=MAX_PROFILE_ITEMS)
    domain_knowledge: list[str] = Field(default_factory=list, max_length=MAX_PROFILE_ITEMS)
    education: list[str] = Field(default_factory=list, max_length=MAX_PROFILE_ITEMS)
    languages: list[str] = Field(default_factory=list, max_length=MAX_PROFILE_ITEMS)
    technical_competencies: list[str] = Field(default_factory=list, max_length=MAX_PROFILE_ITEMS)
    assumptions_to_validate: list[str] = Field(default_factory=list, max_length=MAX_PROFILE_ITEMS)

    @field_validator(
        "required_technologies",
        "preferred_technologies",
        "required_certifications",
        "preferred_certifications",
        "specific_experience",
        "responsibilities",
        "domain_knowledge",
        "education",
        "languages",
        "technical_competencies",
        "assumptions_to_validate",
    )
    @classmethod
    def bound_profile_items(cls, values: list[str]) -> list[str]:
        for value in values:
            if len(str(value)) > MAX_PROFILE_ITEM_CHARS:
                raise ValueError("profile item too long")
        return values


class JobEnrichmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["enrich", "improve"] = "enrich"
    title: str = Field(min_length=1, max_length=MAX_JOB_TITLE_CHARS)
    description: str | None = Field(default=None, max_length=MAX_JOB_DESCRIPTION_CHARS)
    country_code: str | None = None
    company_name: str | None = Field(default=None, max_length=160)
    city: str | None = None
    employment_type: str | None = None
    work_mode: Literal["ONSITE", "HYBRID", "REMOTE"] = "ONSITE"
    evaluation_profile: EvaluationProfile | None = None


class JobEnrichmentProposal(EvaluationProfile):
    improved_description: str = Field(min_length=1, max_length=MAX_JOB_DESCRIPTION_CHARS)


class CreateJobRequest(BaseModel):
    title: str = Field(min_length=1, max_length=MAX_JOB_TITLE_CHARS)
    description: str | None = Field(default=None, max_length=MAX_JOB_DESCRIPTION_CHARS)
    indeed_description: str | None = Field(default=None, max_length=MAX_JOB_DESCRIPTION_CHARS)
    ai_description: str | None = Field(default=None, max_length=MAX_JOB_DESCRIPTION_CHARS)
    active_description_source: Literal["indeed", "ai"] = "indeed"
    country_code: str | None = None
    company_name: str | None = Field(default=None, max_length=160)
    city: str | None = None
    employment_type: str | None = None
    work_mode: Literal["ONSITE", "HYBRID", "REMOTE"] = "ONSITE"
    response_time_business_days: int = Field(default=2, ge=0, le=30)
    phone_call_count: int = Field(default=1, ge=0, le=10)
    onsite_interview_count: int = Field(default=1, ge=0, le=10)
    offer_wait_days: int = Field(default=4, ge=0, le=30)
    offer_wait_reference: Literal["AFTER_INTERVIEW"] = "AFTER_INTERVIEW"
    public_slug: str | None = None
    published_at: datetime | None = None
    evaluation_profile: EvaluationProfile | None = None


class UpdateJobRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=MAX_JOB_TITLE_CHARS)
    description: str | None = Field(default=None, max_length=MAX_JOB_DESCRIPTION_CHARS)
    indeed_description: str | None = Field(default=None, max_length=MAX_JOB_DESCRIPTION_CHARS)
    ai_description: str | None = Field(default=None, max_length=MAX_JOB_DESCRIPTION_CHARS)
    active_description_source: Literal["indeed", "ai"] | None = None
    country_code: str | None = None
    company_name: str | None = Field(default=None, max_length=160)
    city: str | None = None
    employment_type: str | None = None
    work_mode: Literal["ONSITE", "HYBRID", "REMOTE"] | None = None
    response_time_business_days: int | None = Field(default=None, ge=0, le=30)
    phone_call_count: int | None = Field(default=None, ge=0, le=10)
    onsite_interview_count: int | None = Field(default=None, ge=0, le=10)
    offer_wait_days: int | None = Field(default=None, ge=0, le=30)
    offer_wait_reference: Literal["AFTER_INTERVIEW"] | None = None
    public_slug: str | None = None
    published_at: datetime | None = None
    evaluation_profile: EvaluationProfile | None = None


class SetJobStatusRequest(BaseModel):
    status: Literal["ACTIVE", "PAUSED"]


class JobResponse(BaseModel):
    job_id: str
    id: str
    title: str
    description: str | None = None
    indeed_description: str | None = None
    ai_description: str | None = None
    active_description_source: Literal["indeed", "ai"] = "indeed"
    status: Literal["ACTIVE", "PAUSED"] = "ACTIVE"
    country_code: str | None = None
    company_name: str | None = Field(default=None, max_length=160)
    city: str | None = None
    employment_type: str | None = None
    work_mode: Literal["ONSITE", "HYBRID", "REMOTE"] = "ONSITE"
    response_time_business_days: int = 2
    phone_call_count: int = 1
    onsite_interview_count: int = 1
    offer_wait_days: int = 4
    offer_wait_reference: Literal["AFTER_INTERVIEW"] = "AFTER_INTERVIEW"
    public_slug: str | None = None
    published_at: str | None = None
    created_at: str | None = None
    candidate_count: int = 0
    evaluation_version: int = 1
    evaluation_profile: dict = Field(default_factory=dict)
    evaluation_changed: bool = False
    reevaluation_scheduled: bool = False
    reevaluation_candidate_count: int = 0

    model_config = {"from_attributes": True}


class DeleteJobResponse(BaseModel):
    detail: str
    job_id: str
    delete_candidates: bool
    deleted_candidates: int


class AssignCandidatesRequest(BaseModel):
    candidate_ids: list[str]
