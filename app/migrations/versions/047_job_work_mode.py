"""add work mode to vacancies

Revision ID: 047
Revises: 046
Create Date: 2026-10-07
"""

from alembic import op
import sqlalchemy as sa


revision = "047"
down_revision = "046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column(
            "work_mode",
            sa.Text(),
            nullable=False,
            server_default="ONSITE",
        ),
    )
    op.create_check_constraint(
        "ck_jobs_work_mode",
        "jobs",
        "work_mode IN ('ONSITE', 'HYBRID', 'REMOTE')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_jobs_work_mode", "jobs", type_="check")
    op.drop_column("jobs", "work_mode")
