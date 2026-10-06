"""Schemas for employee administration."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator


RoleCode = Literal["ADMIN", "EMPLOYEE"]
EmployeeStatus = Literal["ACTIVE", "DISABLED"]


class CreateEmployeeRequest(BaseModel):
    username: str = Field(min_length=3, max_length=40)
    email: str = Field(min_length=3, max_length=320)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    job_title: str | None = Field(default=None, max_length=160)
    department: str | None = Field(default=None, max_length=160)
    country_code: str | None = Field(default=None, max_length=2)
    company_name: str | None = Field(default=None, max_length=160)
    hire_date: date | None = None
    role: RoleCode = "EMPLOYEE"

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

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if normalized.count("@") != 1:
            raise ValueError("invalid email")
        local, domain = normalized.split("@", 1)
        if not local or not domain or "." not in domain:
            raise ValueError("invalid email")
        return normalized

    @field_validator("first_name", "last_name")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("job_title", "department", "company_name")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


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

class UpdateEmployeeRequest(BaseModel):
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    job_title: str | None = Field(default=None, max_length=160)
    department: str | None = Field(default=None, max_length=160)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    company_name: str | None = Field(default=None, max_length=160)
    hire_date: date | None = None

    @field_validator("first_name", "last_name", "job_title", "department", "company_name")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None




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

class SetEmployeeRoleRequest(BaseModel):
    role: RoleCode


class SetEmployeeStatusRequest(BaseModel):
    status: EmployeeStatus


class SetEmployeeUsernameRequest(BaseModel):
    username: str = Field(min_length=3, max_length=40)

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
