"""add biometric clock identity to employee attendance settings

Revision ID: 046
Revises: 045
Create Date: 2026-10-06
"""

from alembic import op
import sqlalchemy as sa


revision = "046"
down_revision = "045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "talent_employee_attendance_settings",
        sa.Column("biometric_user_id", sa.Text(), nullable=True),
    )
    op.create_index(
        "idx_talent_employee_attendance_settings_biometric_user_id",
        "talent_employee_attendance_settings",
        ["biometric_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_talent_employee_attendance_settings_biometric_user_id",
        table_name="talent_employee_attendance_settings",
    )
    op.drop_column(
        "talent_employee_attendance_settings",
        "biometric_user_id",
    )
