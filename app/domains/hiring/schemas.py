"""Schemas for candidate-to-employee hiring."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator


class HireContractRequest(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    contract_type: str = Field(min_length=1, max_length=160)
    start_date: date
    end_date: date | None = None
    monthly_wage: Decimal = Field(gt=0, decimal_places=2)

    @field_validator("name")
    @classmethod
    def strip_contract_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("contract_type")
    @classmethod
    def strip_contract_type(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("contract type is required")
        return normalized

    @model_validator(mode="after")
    def validate_contract_dates(self):
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("contract end date must be on or after start date")
        return self


class HireCandidateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=40)
    email: str | None = Field(default=None, max_length=320)
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    job_title: str | None = Field(default=None, max_length=160)
    department: str | None = Field(default=None, max_length=160)
    country_code: str | None = Field(default=None, max_length=2)
    company_name: str | None = Field(default=None, max_length=160)
    hire_date: date | None = None
    contract: HireContractRequest | None = None

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

    @field_validator("country_code")
    @classmethod
    def normalize_country_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        if not normalized:
            return None
        if len(normalized) != 2 or not normalized.isalpha():
            raise ValueError("invalid country code")
        return normalized

    @field_validator("email", "first_name", "last_name", "job_title", "department", "company_name")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None
