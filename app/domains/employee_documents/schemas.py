"""Request schemas for employee document workflows."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


DocumentType = Literal["CONTRACT", "ADDENDUM", "OTHER"]


class CreateEmployeeDocumentRequest(BaseModel):
    document_type: Literal["ADDENDUM", "OTHER"]
    title: str = Field(min_length=1, max_length=200)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        return value.strip()


class GenerateEmployeeDocumentRequest(BaseModel):
    manual_values: dict[str, str] = Field(default_factory=dict)


class VoidEmployeeDocumentRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return value.strip()


class SignedDocumentMetadata(BaseModel):
    signed_at: datetime | None = None
