"""add employee self-service personal profiles and document requests

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
    op.create_table(
        "employee_personal_profiles",
        sa.Column("employee_id", sa.Text(), nullable=False),
        sa.Column("personal_email", sa.Text(), nullable=True),
        sa.Column("phone", sa.Text(), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("city", sa.Text(), nullable=True),
        sa.Column("emergency_contact_name", sa.Text(), nullable=True),
        sa.Column("emergency_contact_phone", sa.Text(), nullable=True),
        sa.Column("updated_by_sub", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["user_profiles.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("employee_id"),
    )

    op.create_table(
        "employee_document_requests",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("employee_id", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("document_type", sa.Text(), nullable=True),
        sa.Column(
            "required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("requested_by_sub", sa.Text(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=True),
        sa.Column("original_filename", sa.Text(), nullable=True),
        sa.Column("content_type", sa.Text(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.Text(), nullable=True),
        sa.Column("uploaded_by_sub", sa.Text(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'UPLOADED')",
            name="ck_employee_document_requests_status",
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["user_profiles.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "storage_key",
            name="uq_employee_document_requests_storage_key",
        ),
    )
    op.create_index(
        "idx_employee_document_requests_employee_status",
        "employee_document_requests",
        ["employee_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_employee_document_requests_employee_status",
        table_name="employee_document_requests",
    )
    op.drop_table("employee_document_requests")
    op.drop_table("employee_personal_profiles")
