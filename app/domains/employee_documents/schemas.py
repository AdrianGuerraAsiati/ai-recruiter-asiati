"""Request schemas for employee intake submissions and review."""

from typing import Literal

from pydantic import BaseModel, Field


class CreateEmployeeDocumentUploadRequest(BaseModel):
    document_type: str = Field(..., min_length=1, max_length=80)
    filename: str = Field(..., min_length=1, max_length=240)
    content_type: str = Field(..., min_length=1, max_length=120)
    size_bytes: int = Field(..., gt=0)


class FinalizeEmployeeDocumentUploadRequest(CreateEmployeeDocumentUploadRequest):
    key: str = Field(..., min_length=1, max_length=1000)


class SaveEmployeeDocumentValueRequest(BaseModel):
    document_type: str = Field(..., min_length=1, max_length=80)
    value: str = Field(..., min_length=1, max_length=2000)


class ReviewEmployeeDocumentRequest(BaseModel):
    status: Literal["APPROVED", "CHANGES_REQUESTED"]
    comment: str | None = Field(default=None, max_length=2000)


class ConfirmContractSignPreparation(BaseModel):
    # Avoid implicit writes triggered by re-fetching a read-only endpoint.
    confirm: Literal[True]


class LinkStagingSignRequest(BaseModel):
    # Explicit HR request only. IDs are checked against staged template + signers.
    request_id: int = Field(..., gt=0)
    confirm: Literal[True]


class PreviewOdooSignRequest(BaseModel):
    """Preflight only: numeric Odoo res.partner IDs, no write or mail."""
    employee_partner_id: int = Field(..., gt=0)
    representative_partner_id: int = Field(..., gt=0)
