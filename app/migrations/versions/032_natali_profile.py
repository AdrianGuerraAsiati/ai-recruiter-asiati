"""complete Natalí Garzón employee profile

Revision ID: 032
Revises: 031
Create Date: 2026-09-30
"""

from alembic import op
import sqlalchemy as sa


revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE user_profiles
            SET job_title = 'COO LATAM',
                department = 'Global Team'
            WHERE lower(email) = 'natali.garzon@asiati.com.co'
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE user_profiles
            SET job_title = NULL,
                department = NULL
            WHERE lower(email) = 'natali.garzon@asiati.com.co'
              AND job_title = 'COO LATAM'
              AND department = 'Global Team'
            """
        )
    )
