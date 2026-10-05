"""track Talent ID biometric provider cleanup

Revision ID: 043
Revises: 042
Create Date: 2026-10-05
"""

from alembic import op
import sqlalchemy as sa


revision = "043"
down_revision = "042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "talent_biometric_enrollments",
        sa.Column(
            "provider_cleanup_pending",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "talent_biometric_enrollments",
        sa.Column("provider_cleanup_last_error", sa.Text(), nullable=True),
    )
    op.add_column(
        "talent_biometric_enrollments",
        sa.Column(
            "provider_cleanup_attempted_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "talent_biometric_enrollments",
        "provider_cleanup_attempted_at",
    )
    op.drop_column(
        "talent_biometric_enrollments",
        "provider_cleanup_last_error",
    )
    op.drop_column(
        "talent_biometric_enrollments",
        "provider_cleanup_pending",
    )
