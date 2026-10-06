"""add country and company to employees and vacancies

Revision ID: 045
Revises: 044
Create Date: 2026-10-06
"""

from alembic import op
import sqlalchemy as sa


revision = "045"
down_revision = "044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_profiles", sa.Column("country_code", sa.Text(), nullable=True))
    op.add_column("user_profiles", sa.Column("company_name", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("company_name", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "company_name")
    op.drop_column("user_profiles", "company_name")
    op.drop_column("user_profiles", "country_code")
