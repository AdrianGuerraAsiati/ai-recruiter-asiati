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
    Uuid,
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
        CheckConstraint(
            "odoo_sign_status IN ('NOT_PREPARED', 'PREPARING', 'PREPARED', 'FAILED')",
            name="ck_employee_documents_odoo_sign_status",
        ),
        CheckConstraint(
            "odoo_sign_request_status IN ('UNLINKED', 'PENDING_SIGNATURE', 'PARTIALLY_SIGNED', 'SIGNED', 'CANCELLED', 'EXPIRED')",
            name="ck_employee_documents_odoo_sign_request_status",
        ),
        CheckConstraint("odoo_sign_environment IS NULL OR odoo_sign_environment IN ('staging', 'production')", name="ck_employee_documents_odoo_sign_environment"),
        UniqueConstraint("odoo_sign_request_id", name="uq_employee_documents_odoo_sign_request_id"),
        CheckConstraint("odoo_sign_dispatch_status IN ('NOT_SENT', 'DISPATCHING', 'SENT', 'UNKNOWN')", name="ck_employee_documents_odoo_sign_dispatch_status"),
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

    # A prepared Sign template does not mean an email was sent or a signature exists.
    odoo_sign_environment = Column(Text, nullable=True)
    odoo_sign_template_id = Column(Integer, nullable=True)
    odoo_sign_attachment_id = Column(Integer, nullable=True)
    odoo_sign_source_key = Column(Text, nullable=True)
    odoo_sign_status = Column(Text, nullable=False, default="NOT_PREPARED")
    odoo_sign_prepared_at = Column(DateTime(timezone=True), nullable=True)
    # Only validated Sign requests are tracked. These values are NOT proof
    # of delivery, legal validity, or archival of a signed PDF.
    # Network timeout cannot safely be retried: UNKNOWN requires reconciliation.
    odoo_sign_dispatch_status = Column(Text, nullable=False, default="NOT_SENT")
    odoo_sign_dispatch_subject = Column(Text, nullable=True)
    odoo_sign_dispatch_started_at = Column(DateTime(timezone=True), nullable=True)
    odoo_sign_dispatch_wizard_id = Column(Integer, nullable=True)
    odoo_sign_request_id = Column(Integer, nullable=True)
    odoo_sign_request_status = Column(Text, nullable=False, default="UNLINKED")
    odoo_sign_employee_state = Column(Text, nullable=True)
    odoo_sign_representative_state = Column(Text, nullable=True)
    odoo_sign_checked_at = Column(DateTime(timezone=True), nullable=True)
    odoo_sign_completed_at = Column(DateTime(timezone=True), nullable=True)
    # Immutable signed artifact stored separately from the unsigned contract.
    odoo_sign_signed_storage_key = Column(Text, nullable=True)
    odoo_sign_signed_sha256 = Column(Text, nullable=True)
    odoo_sign_signed_attachment_id = Column(Integer, nullable=True)
    odoo_sign_signed_at = Column(DateTime(timezone=True), nullable=True)
    # Separate, immutable completion certificate linked to the same Sign request.
    odoo_sign_certificate_storage_key = Column(Text, nullable=True)
    odoo_sign_certificate_sha256 = Column(Text, nullable=True)
    odoo_sign_certificate_attachment_id = Column(Integer, nullable=True)

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


class ApplicationContract(Base):
    """Associate one signed contract document with exactly one job application.

    Legacy employee documents stay untouched and do not automatically acquire
    an application binding merely because employee_id matches.
    """

    __tablename__ = "application_contracts"
    __table_args__ = (
        UniqueConstraint("document_id", name="uq_application_contracts_document"),
        CheckConstraint("odoo_company_id > 0", name="ck_application_contracts_company_positive"),
        Index("idx_application_contracts_employee", "employee_id"),
    )

    application_id = Column(
        Uuid(as_uuid=False),
        ForeignKey("job_candidates.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    employee_id = Column(Text, ForeignKey("user_profiles.id", ondelete="RESTRICT"), nullable=False)
    document_id = Column(Text, ForeignKey("employee_documents.id", ondelete="RESTRICT"), nullable=False)
    odoo_company_id = Column(Integer, nullable=False)
    source_storage_key = Column(Text, nullable=False)
    bound_at = Column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    application = relationship("JobCandidate")
    employee = relationship("UserProfile")
    document = relationship("EmployeeDocument")
