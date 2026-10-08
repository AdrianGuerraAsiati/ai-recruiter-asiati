"""Request schemas for private employee document uploads."""

from pydantic import BaseModel, Field


class CreateEmployeeDocumentUploadRequest(BaseModel):
    document_type: str = Field(..., min_length=1, max_length=80)
    filename: str = Field(..., min_length=1, max_length=240)
    content_type: str = Field(..., min_length=1, max_length=120)
    size_bytes: int = Field(..., gt=0)


class FinalizeEmployeeDocumentUploadRequest(CreateEmployeeDocumentUploadRequest):
    key: str = Field(..., min_length=1, max_length=1000)
