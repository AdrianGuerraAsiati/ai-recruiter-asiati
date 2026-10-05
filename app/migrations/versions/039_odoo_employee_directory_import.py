"""allow Odoo employee directory imports without Cognito access

Revision ID: 039
Revises: 038
Create Date: 2026-10-05
"""

from alembic import op
import sqlalchemy as sa


revision = "039"
down_revision = "038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "user_profiles",
        "cognito_sub",
        existing_type=sa.Text(),
        nullable=True,
    )
    op.alter_column(
        "user_profiles",
        "email",
        existing_type=sa.Text(),
        nullable=True,
    )
    op.add_column(
        "user_profiles",
        sa.Column("odoo_employee_id", sa.Text(), nullable=True),
    )
    op.create_unique_constraint(
        "uq_user_profiles_odoo_employee_id",
        "user_profiles",
        ["odoo_employee_id"],
    )
    op.create_index(
        "idx_user_profiles_odoo_employee_id",
        "user_profiles",
        ["odoo_employee_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_user_profiles_odoo_employee_id",
        table_name="user_profiles",
    )
    op.drop_constraint(
        "uq_user_profiles_odoo_employee_id",
        "user_profiles",
        type_="unique",
    )
    op.drop_column("user_profiles", "odoo_employee_id")
    op.alter_column(
        "user_profiles",
        "email",
        existing_type=sa.Text(),
        nullable=False,
    )
    op.alter_column(
        "user_profiles",
        "cognito_sub",
        existing_type=sa.Text(),
        nullable=False,
    )
