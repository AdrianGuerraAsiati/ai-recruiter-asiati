"""ORM models for employee document lifecycle."""

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
from sqlalchemy.dialects.postgresql import UUID

from app.db import Base


class EmployeeDocument(Base):
    """Logical employee document across generated and signed versions."""

    __tablename__ = "employee_documents"
    __table_args__ = (
        CheckConstraint(
            "document_type IN ('CONTRACT', 'ADDENDUM', 'OTHER')",
            name="ck_employee_documents_document_type",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'PENDING_SIGNATURE', 'SIGNED', 'VOID')",
            name="ck_employee_documents_status",
        ),
        UniqueConstraint(
            "contract_sync_id",
            name="uq_employee_documents_contract_sync",
        ),
        Index(
            "idx_employee_documents_employee_status",
            "employee_id",
            "status",
        ),
    )

    id = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    employee_id = Column(
        Text,
        ForeignKey("user_profiles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    document_type = Column(Text, nullable=False)
    title = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="DRAFT")
    contract_sync_id = Column(
        UUID(as_uuid=False),
        ForeignKey("odoo_contract_syncs.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_job_candidate_id = Column(
        UUID(as_uuid=False),
        ForeignKey("job_candidates.id", ondelete="SET NULL"),
        nullable=True,
    )
    current_signed_version_id = Column(
        UUID(as_uuid=False),
        ForeignKey(
            "employee_document_versions.id",
            name="fk_employee_documents_current_signed_version",
            ondelete="SET NULL",
            use_alter=True,
        ),
        nullable=True,
    )
    created_by_sub = Column(Text, nullable=False)
    voided_by_sub = Column(Text, nullable=True)
    voided_at = Column(DateTime(timezone=True), nullable=True)
    void_reason = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class EmployeeDocumentArtifact(Base):
    """Generated non-authoritative DOCX/PDF output."""

    __tablename__ = "employee_document_artifacts"
    __table_args__ = (
        CheckConstraint(
            "artifact_kind IN ('GENERATED_DOCX', 'REFERENCE_PDF')",
            name="ck_employee_document_artifacts_kind",
        ),
        UniqueConstraint(
            "storage_key",
            name="uq_employee_document_artifacts_storage_key",
        ),
        Index(
            "idx_employee_document_artifacts_document_created",
            "document_id",
            "created_at",
        ),
    )

    id = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    document_id = Column(
        UUID(as_uuid=False),
        ForeignKey("employee_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    artifact_kind = Column(Text, nullable=False)
    storage_key = Column(Text, nullable=False)
    mime_type = Column(Text, nullable=False)
    file_size = Column(Integer, nullable=False)
    sha256 = Column(Text, nullable=False)
    template_version = Column(Text, nullable=False)
    created_by_sub = Column(Text, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class EmployeeDocumentVersion(Base):
    """Immutable signed-PDF evidence version."""

    __tablename__ = "employee_document_versions"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "version_number",
            name="uq_employee_document_versions_document_version",
        ),
        UniqueConstraint(
            "storage_key",
            name="uq_employee_document_versions_storage_key",
        ),
        Index(
            "idx_employee_document_versions_document_created",
            "document_id",
            "created_at",
        ),
    )

    id = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    document_id = Column(
        UUID(as_uuid=False),
        ForeignKey("employee_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number = Column(Integer, nullable=False)
    storage_key = Column(Text, nullable=False)
    original_filename = Column(Text, nullable=False)
    mime_type = Column(Text, nullable=False)
    file_size = Column(Integer, nullable=False)
    sha256 = Column(Text, nullable=False)
    signed_at = Column(DateTime(timezone=True), nullable=True)
    uploaded_by_sub = Column(Text, nullable=False)
    uploaded_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    superseded_at = Column(DateTime(timezone=True), nullable=True)
    superseded_by_version_id = Column(
        UUID(as_uuid=False),
        ForeignKey(
            "employee_document_versions.id",
            name="fk_employee_document_versions_superseded_by",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
