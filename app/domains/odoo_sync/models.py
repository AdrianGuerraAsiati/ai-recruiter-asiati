"""ORM models for Odoo synchronization."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from app.db import Base


class OdooEmployeeSync(Base):
    """Durable idempotent state for an employee upsert to Odoo."""

    __tablename__ = "odoo_employee_syncs"
    __table_args__ = (
        UniqueConstraint(
            "employee_id",
            name="uq_odoo_employee_syncs_employee",
        ),
        UniqueConstraint(
            "idempotency_key",
            name="uq_odoo_employee_syncs_idempotency_key",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'SYNCED', 'FAILED')",
            name="ck_odoo_employee_syncs_status",
        ),
        Index(
            "idx_odoo_employee_syncs_status_updated",
            "status",
            "updated_at",
        ),
    )

    id = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    employee_id = Column(
        Text,
        ForeignKey("user_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_job_candidate_id = Column(
        UUID(as_uuid=False),
        ForeignKey("job_candidates.id", ondelete="SET NULL"),
        nullable=True,
    )
    idempotency_key = Column(Text, nullable=False)
    payload = Column(JSON, nullable=False, default=dict)
    status = Column(Text, nullable=False, default="PENDING")
    attempt_count = Column(Integer, nullable=False, default=0)
    odoo_record_id = Column(Text, nullable=True)
    last_error = Column(Text, nullable=True)
    synced_at = Column(DateTime(timezone=True), nullable=True)
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
