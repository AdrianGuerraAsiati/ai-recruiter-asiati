"""ORM model for private employee documents."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.db import Base


class EmployeeDocument(Base):
    """Latest uploaded document for one employee/document type."""

    __tablename__ = "employee_documents"
    __table_args__ = (
        UniqueConstraint(
            "employee_id",
            "document_type",
            name="uq_employee_documents_employee_type",
        ),
        UniqueConstraint("storage_key", name="uq_employee_documents_storage_key"),
        Index("idx_employee_documents_employee_uploaded", "employee_id", "uploaded_at"),
    )

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    employee_id = Column(
        Text,
        ForeignKey("user_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_type = Column(Text, nullable=False)
    original_filename = Column(Text, nullable=False)
    storage_key = Column(Text, nullable=False)
    content_type = Column(Text, nullable=False)
    size_bytes = Column(Integer, nullable=False)
    uploaded_by_sub = Column(Text, nullable=False)
    uploaded_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    employee = relationship("UserProfile")
