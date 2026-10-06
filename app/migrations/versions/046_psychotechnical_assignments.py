"""add psychotechnical assessment assignments

Revision ID: 046
Revises: 045
Create Date: 2026-10-06
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "046"
down_revision = "045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "psychotechnical_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("test_key", sa.Text(), nullable=False),
        sa.Column("test_version", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("answers", sa.JSON(), nullable=True),
        sa.Column("score_total", sa.Integer(), nullable=True),
        sa.Column("dimension_scores", sa.JSON(), nullable=True),
        sa.Column("created_by_sub", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_psychotechnical_token_hash"),
    )
    op.create_index(
        "idx_psychotechnical_candidate_created",
        "psychotechnical_assignments",
        ["candidate_id", "created_at"],
    )
    op.create_index(
        "idx_psychotechnical_status_expires",
        "psychotechnical_assignments",
        ["status", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_psychotechnical_status_expires",
        table_name="psychotechnical_assignments",
    )
    op.drop_index(
        "idx_psychotechnical_candidate_created",
        table_name="psychotechnical_assignments",
    )
    op.drop_table("psychotechnical_assignments")
