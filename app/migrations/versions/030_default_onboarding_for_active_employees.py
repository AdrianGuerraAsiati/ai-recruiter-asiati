"""require onboarding by default for active employee profiles

Revision ID: 030
Revises: 029
Create Date: 2026-09-28
"""

from alembic import op
import sqlalchemy as sa


revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE user_profiles
            SET onboarding_status = 'PENDING',
                onboarding_started_at = NULL,
                onboarding_completed_at = NULL
            WHERE status = 'ACTIVE'
              AND onboarding_status = 'NOT_REQUIRED'
            """
        )
    )


def downgrade() -> None:
    # Data-only backfill: a safe downgrade cannot distinguish profiles that were
    # previously exempt from those that became required by this migration.
    pass
