"""link hired applications to employee profiles

Revision ID: 025
Revises: 024
Create Date: 2026-09-25
"""

from alembic import op
import sqlalchemy as sa


revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "job_candidates",
        sa.Column("employee_id", sa.Text(), nullable=True),
    )
    op.add_column(
        "job_candidates",
        sa.Column("hired_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_job_candidates_employee_id_user_profiles",
        "job_candidates",
        "user_profiles",
        ["employee_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "idx_job_candidates_employee_id",
        "job_candidates",
        ["employee_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_job_candidates_employee_id",
        table_name="job_candidates",
    )
    op.drop_constraint(
        "fk_job_candidates_employee_id_user_profiles",
        "job_candidates",
        type_="foreignkey",
    )
    op.drop_column("job_candidates", "hired_at")
    op.drop_column("job_candidates", "employee_id")
