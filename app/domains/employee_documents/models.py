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
