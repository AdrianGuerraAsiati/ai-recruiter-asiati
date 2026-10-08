"""add private employee documents

Revision ID: 050
Revises: 049
Create Date: 2026-10-08
"""

from alembic import op
import sqlalchemy as sa


revision = "050"
down_revision = "049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "employee_documents",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("employee_id", sa.Text(), nullable=False),
        sa.Column("document_type", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("uploaded_by_sub", sa.Text(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["employee_id"], ["user_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("employee_id", "document_type", name="uq_employee_documents_employee_type"),
        sa.UniqueConstraint("storage_key", name="uq_employee_documents_storage_key"),
    )
    op.create_index(
        "idx_employee_documents_employee_uploaded",
        "employee_documents",
        ["employee_id", "uploaded_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_employee_documents_employee_uploaded", table_name="employee_documents")
    op.drop_table("employee_documents")
