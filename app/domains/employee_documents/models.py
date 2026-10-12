"""ORM model for private employee intake documents and information."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.db import Base


class EmployeeDocument(Base):
    """Latest submission for one employee intake requirement."""

    __tablename__ = "employee_documents"
    __table_args__ = (
        UniqueConstraint(
            "employee_id",
            "document_type",
            name="uq_employee_documents_employee_type",
        ),
        UniqueConstraint("storage_key", name="uq_employee_documents_storage_key"),
        CheckConstraint(
            "review_status IN ('PENDING_REVIEW', 'APPROVED', 'CHANGES_REQUESTED')",
            name="ck_employee_documents_review_status",
        ),
        Index("idx_employee_documents_employee_uploaded", "employee_id", "uploaded_at"),
        Index("idx_employee_documents_employee_review", "employee_id", "review_status"),
    )

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    employee_id = Column(
        Text,
        ForeignKey("user_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_type = Column(Text, nullable=False)
    original_filename = Column(Text, nullable=True)
    storage_key = Column(Text, nullable=True)
    content_type = Column(Text, nullable=True)
    size_bytes = Column(Integer, nullable=True)
    value_text = Column(Text, nullable=True)
    uploaded_by_sub = Column(Text, nullable=True)
    uploaded_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    review_status = Column(Text, nullable=False, default="PENDING_REVIEW")
    review_comment = Column(Text, nullable=True)
    reviewed_by_sub = Column(Text, nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)

    employee = relationship("UserProfile")


class EmployeeDocumentEmail(Base):
    """One durable welcome-document request per employee (safe to retry)."""

    __tablename__ = "employee_document_emails"
    __table_args__ = (
        UniqueConstraint("employee_id", "kind", name="uq_employee_document_emails_employee_kind"),
        CheckConstraint(
            "status IN ('PENDING', 'SENDING', 'SENT', 'FAILED')",
            name="ck_employee_document_emails_status",
        ),
        Index("idx_employee_document_emails_status", "status", "created_at"),
    )

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    employee_id = Column(
        Text,
        ForeignKey("user_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind = Column(Text, nullable=False, default="WELCOME_DOCUMENTS")
    status = Column(Text, nullable=False, default="PENDING")
    attempt_count = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    attempt_at = Column(DateTime(timezone=True), nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)

    employee = relationship("UserProfile")
