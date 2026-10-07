"""allow durable ranking reevaluation scope and force mode

Revision ID: 049
Revises: 048
Create Date: 2026-10-07
"""

from alembic import op
import sqlalchemy as sa


revision = "049"
down_revision = "048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "job_reevaluation_tasks",
        sa.Column(
            "scope",
            sa.Text(),
            nullable=False,
            server_default="assigned",
        ),
    )
    op.add_column(
        "job_reevaluation_tasks",
        sa.Column(
            "force_evaluation",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("job_reevaluation_tasks", "force_evaluation")
    op.drop_column("job_reevaluation_tasks", "scope")
