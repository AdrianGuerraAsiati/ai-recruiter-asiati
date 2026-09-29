"""persist system-managed training course identity

Revision ID: 031
Revises: 030
Create Date: 2026-09-29
"""

from alembic import op
import sqlalchemy as sa


revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "training_courses",
        sa.Column(
            "managed_by_system",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.execute(
        sa.text(
            """
            UPDATE training_courses
            SET managed_by_system = TRUE
            WHERE is_onboarding = TRUE
              AND title = 'Onboarding ASIATI'
            """
        )
    )


def downgrade() -> None:
    op.drop_column("training_courses", "managed_by_system")
