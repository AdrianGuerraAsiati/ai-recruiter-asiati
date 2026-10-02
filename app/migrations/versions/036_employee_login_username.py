"""add employee login username

Revision ID: 036
Revises: 035
Create Date: 2026-10-02
"""

from alembic import op
import sqlalchemy as sa


revision = "036"
down_revision = "035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_profiles",
        sa.Column("login_username", sa.Text(), nullable=True),
    )
    op.create_unique_constraint(
        "uq_user_profiles_login_username",
        "user_profiles",
        ["login_username"],
    )
    op.create_index(
        "idx_user_profiles_login_username",
        "user_profiles",
        ["login_username"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_user_profiles_login_username", table_name="user_profiles")
    op.drop_constraint(
        "uq_user_profiles_login_username",
        "user_profiles",
        type_="unique",
    )
    op.drop_column("user_profiles", "login_username")
