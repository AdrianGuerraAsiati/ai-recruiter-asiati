"""add vacancy active paused status

Revision ID: 035
Revises: 034
Create Date: 2026-10-01
"""

from alembic import op
import sqlalchemy as sa


revision = "035"
down_revision = "034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default="ACTIVE",
        ),
    )


def downgrade() -> None:
    op.drop_column("jobs", "status")
