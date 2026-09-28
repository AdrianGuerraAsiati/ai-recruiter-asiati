"""add recruitment calendar events

Revision ID: 027
Revises: 026
Create Date: 2026-09-28
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recruitment_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            nullable=False,
        ),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=False),
            nullable=False,
        ),
        sa.Column(
            "candidate_id",
            postgresql.UUID(as_uuid=False),
            nullable=False,
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default="SCHEDULED",
        ),
        sa.Column("created_by_sub", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "kind IN ('PHONE_CALL', 'ONSITE_INTERVIEW')",
            name="ck_recruitment_events_kind",
        ),
        sa.CheckConstraint(
            "status IN ('SCHEDULED', 'COMPLETED', 'CANCELED')",
            name="ck_recruitment_events_status",
        ),
        sa.CheckConstraint(
            "ends_at > starts_at",
            name="ck_recruitment_events_window",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidates.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_recruitment_events_start",
        "recruitment_events",
        ["starts_at"],
        unique=False,
    )
    op.create_index(
        "idx_recruitment_events_job_start",
        "recruitment_events",
        ["job_id", "starts_at"],
        unique=False,
    )
    op.create_index(
        "idx_recruitment_events_candidate_start",
        "recruitment_events",
        ["candidate_id", "starts_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_recruitment_events_candidate_start",
        table_name="recruitment_events",
    )
    op.drop_index(
        "idx_recruitment_events_job_start",
        table_name="recruitment_events",
    )
    op.drop_index(
        "idx_recruitment_events_start",
        table_name="recruitment_events",
    )
    op.drop_table("recruitment_events")
