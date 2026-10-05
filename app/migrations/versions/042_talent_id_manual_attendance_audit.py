"""add Talent ID manual attendance audit fields

Revision ID: 042
Revises: 041
Create Date: 2026-10-05
"""

from alembic import op
import sqlalchemy as sa


revision = "042"
down_revision = "041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "talent_attendance_events",
        sa.Column("manual_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "talent_attendance_events",
        sa.Column("created_by_sub", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("talent_attendance_events", "created_by_sub")
    op.drop_column("talent_attendance_events", "manual_reason")
