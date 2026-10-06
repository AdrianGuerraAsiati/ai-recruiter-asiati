"""ORM models for employee self-service data and requested documents."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)

from app.db import Base


def _now():
    return datetime.now(timezone.utc)


class EmployeePersonalProfile(Base):
    __tablename__ = "employee_personal_profiles"

    employee_id = Column(
        Text,
        ForeignKey("user_profiles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    personal_email = Column(Text, nullable=True)
    phone = Column(Text, nullable=True)
    address = Column(Text, nullable=True)
    city = Column(Text, nullable=True)
    emergency_contact_name = Column(Text, nullable=True)
    emergency_contact_phone = Column(Text, nullable=True)
    updated_by_sub = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=_now,
        onupdate=_now,
    )


class EmployeeDocumentRequest(Base):
    __tablename__ = "employee_document_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'UPLOADED')",
            name="ck_employee_document_requests_status",
        ),
        UniqueConstraint(
            "storage_key",
            name="uq_employee_document_requests_storage_key",
        ),
        Index(
            "idx_employee_document_requests_employee_status",
            "employee_id",
            "status",
        ),
    )

    id = Column(
        Text,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    employee_id = Column(
        Text,
        ForeignKey("user_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    label = Column(Text, nullable=False)
    document_type = Column(Text, nullable=True)
    required = Column(Boolean, nullable=False, default=True)
    status = Column(Text, nullable=False, default="PENDING")
    requested_by_sub = Column(Text, nullable=False)

    storage_key = Column(Text, nullable=True)
    original_filename = Column(Text, nullable=True)
    content_type = Column(Text, nullable=True)
    size_bytes = Column(Integer, nullable=True)
    sha256 = Column(Text, nullable=True)
    uploaded_by_sub = Column(Text, nullable=True)
    uploaded_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=_now,
        onupdate=_now,
    )
