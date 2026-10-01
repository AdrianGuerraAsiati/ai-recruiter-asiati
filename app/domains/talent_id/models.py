"""SQLAlchemy models for Talent ID inside Talent Intelligence."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    Time,
    UniqueConstraint,
)

from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TalentSite(Base):
    __tablename__ = "talent_sites"
    __table_args__ = (
        UniqueConstraint("code", name="uq_talent_sites_code"),
        Index("idx_talent_sites_active", "active"),
    )

    id = Column(Text, primary_key=True, default=_uuid)
    name = Column(Text, nullable=False)
    code = Column(Text, nullable=True)
    timezone = Column(Text, nullable=False, default="America/Bogota")
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)


class TalentWorkSchedule(Base):
    __tablename__ = "talent_work_schedules"
    __table_args__ = (Index("idx_talent_work_schedules_active", "active"),)

    id = Column(Text, primary_key=True, default=_uuid)
    name = Column(Text, nullable=False)
    start_time = Column(Time(), nullable=False)
    end_time = Column(Time(), nullable=False)
    tolerance_minutes = Column(Integer, nullable=False, default=0)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)


class TalentEmployeeAttendanceSetting(Base):
    """Attendance configuration layered on top of the canonical user profile."""

    __tablename__ = "talent_employee_attendance_settings"

    employee_id = Column(
        Text,
        ForeignKey("user_profiles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    site_id = Column(
        Text,
        ForeignKey("talent_sites.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    schedule_id = Column(
        Text,
        ForeignKey("talent_work_schedules.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    attendance_eligible = Column(Boolean, nullable=False, default=True)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=_now,
        onupdate=_now,
    )


class TalentKioskDevice(Base):
    __tablename__ = "talent_kiosk_devices"
    __table_args__ = (
        Index("idx_talent_kiosk_devices_site_active", "site_id", "active"),
    )

    id = Column(Text, primary_key=True, default=_uuid)
    site_id = Column(
        Text,
        ForeignKey("talent_sites.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name = Column(Text, nullable=False)
    token_hash = Column(Text, nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)


class TalentBiometricEnrollment(Base):
    """Provider identifiers only; raw facial images are not persisted."""

    __tablename__ = "talent_biometric_enrollments"

    employee_id = Column(
        Text,
        ForeignKey("user_profiles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    provider = Column(Text, nullable=False, default="AWS_REKOGNITION")
    provider_user_id = Column(Text, nullable=False, unique=True)
    face_count = Column(Integer, nullable=False, default=0)
    active = Column(Boolean, nullable=False, default=True)
    enrolled_at = Column(DateTime(timezone=True), nullable=False, default=_now)


class TalentAttendanceEvent(Base):
    __tablename__ = "talent_attendance_events"
    __table_args__ = (
        UniqueConstraint(
            "idempotency_key",
            name="uq_talent_attendance_events_idempotency_key",
        ),
        CheckConstraint(
            "event_type IN ('CHECK_IN', 'CHECK_OUT')",
            name="ck_talent_attendance_events_event_type",
        ),
        CheckConstraint(
            "method IN ('FACE', 'PIN', 'QR', 'MANUAL')",
            name="ck_talent_attendance_events_method",
        ),
        Index(
            "idx_talent_attendance_events_employee_date",
            "employee_id",
            "occurred_at",
        ),
        Index(
            "idx_talent_attendance_events_site_date",
            "site_id",
            "occurred_at",
        ),
    )

    id = Column(Text, primary_key=True, default=_uuid)
    employee_id = Column(
        Text,
        ForeignKey("user_profiles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    site_id = Column(
        Text,
        ForeignKey("talent_sites.id", ondelete="RESTRICT"),
        nullable=False,
    )
    device_id = Column(
        Text,
        ForeignKey("talent_kiosk_devices.id", ondelete="SET NULL"),
        nullable=True,
    )
    event_type = Column(Text, nullable=False)
    method = Column(Text, nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    idempotency_key = Column(Text, nullable=False)
    recognition_confidence = Column(Float, nullable=True)
