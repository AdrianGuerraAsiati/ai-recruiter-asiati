"""Schemas for employee self-service and requested documents."""

from pydantic import BaseModel, Field, field_validator


class UpdateOwnProfileRequest(BaseModel):
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    personal_email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = Field(default=None, max_length=300)
    city: str | None = Field(default=None, max_length=120)
    emergency_contact_name: str | None = Field(default=None, max_length=160)
    emergency_contact_phone: str | None = Field(default=None, max_length=50)

    @field_validator(
        "first_name",
        "last_name",
        "personal_email",
        "phone",
        "address",
        "city",
        "emergency_contact_name",
        "emergency_contact_phone",
    )
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("personal_email")
    @classmethod
    def validate_personal_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.casefold()
        if normalized.count("@") != 1:
            raise ValueError("invalid email")
        local, domain = normalized.split("@", 1)
        if not local or not domain or "." not in domain:
            raise ValueError("invalid email")
        return normalized


class CreateDocumentRequest(BaseModel):
    label: str = Field(min_length=2, max_length=160)
    document_type: str | None = Field(default=None, max_length=80)
    required: bool = True

    @field_validator("label", "document_type")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None
