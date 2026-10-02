"""Schemas for candidate-to-employee hiring."""

from datetime import date

from pydantic import BaseModel, Field, field_validator


class HireCandidateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=40)
    email: str | None = Field(default=None, max_length=320)
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    job_title: str | None = Field(default=None, max_length=160)
    department: str | None = Field(default=None, max_length=160)
    hire_date: date | None = None

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        normalized = value.strip().casefold()
        allowed = set("abcdefghijklmnopqrstuvwxyz0123456789._-")
        if not normalized or any(char not in allowed for char in normalized):
            raise ValueError("invalid username")
        if not normalized[0].isalnum() or not normalized[-1].isalnum():
            raise ValueError("invalid username")
        return normalized

    @field_validator("email", "first_name", "last_name", "job_title", "department")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None
