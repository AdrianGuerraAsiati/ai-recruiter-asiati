"""ORM model for objective, non-clinical psychotechnical assessments."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db import Base


class PsychotechnicalAssignment(Base):
    __tablename__ = "psychotechnical_assignments"
    __table_args__ = (
        Index("idx_psychotechnical_candidate_created", "candidate_id", "created_at"),
        Index("idx_psychotechnical_status_expires", "status", "expires_at"),
        UniqueConstraint("token_hash", name="uq_psychotechnical_token_hash"),
    )

    id = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    candidate_id = Column(
        UUID(as_uuid=False),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
    )
    job_id = Column(
        UUID(as_uuid=False),
        ForeignKey("jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    test_key = Column(Text, nullable=False, default="CORE_REASONING_V1")
    test_version = Column(Integer, nullable=False, default=1)
    token_hash = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="PENDING")
    expires_at = Column(DateTime(timezone=True), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    answers = Column(JSON, nullable=True)
    score_total = Column(Integer, nullable=True)
    dimension_scores = Column(JSON, nullable=True)
    created_by_sub = Column(Text, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    candidate = relationship("Candidate")
    job = relationship("Job")
