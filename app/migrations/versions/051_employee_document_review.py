"""add employee document review workflow

Revision ID: 051
Revises: 050
Create Date: 2026-10-08
"""

from alembic import op
import sqlalchemy as sa


revision = "051"
down_revision = "050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "employee_documents",
        "original_filename",
        existing_type=sa.Text(),
        nullable=True,
    )
    op.alter_column(
        "employee_documents",
        "storage_key",
        existing_type=sa.Text(),
        nullable=True,
    )
    op.alter_column(
        "employee_documents",
        "content_type",
        existing_type=sa.Text(),
        nullable=True,
    )
    op.alter_column(
        "employee_documents",
        "size_bytes",
        existing_type=sa.Integer(),
        nullable=True,
    )
    op.alter_column(
        "employee_documents",
        "uploaded_by_sub",
        existing_type=sa.Text(),
        nullable=True,
    )
    op.add_column("employee_documents", sa.Column("value_text", sa.Text(), nullable=True))
    op.add_column(
        "employee_documents",
        sa.Column(
            "review_status",
            sa.Text(),
            nullable=False,
            server_default="PENDING_REVIEW",
        ),
    )
    op.add_column("employee_documents", sa.Column("review_comment", sa.Text(), nullable=True))
    op.add_column("employee_documents", sa.Column("reviewed_by_sub", sa.Text(), nullable=True))
    op.add_column(
        "employee_documents",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_employee_documents_review_status",
        "employee_documents",
        "review_status IN ('PENDING_REVIEW', 'APPROVED', 'CHANGES_REQUESTED')",
    )
    op.create_index(
        "idx_employee_documents_employee_review",
        "employee_documents",
        ["employee_id", "review_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_employee_documents_employee_review",
        table_name="employee_documents",
    )
    op.drop_constraint(
        "ck_employee_documents_review_status",
        "employee_documents",
        type_="check",
    )
    op.execute("DELETE FROM employee_documents WHERE storage_key IS NULL")
    op.drop_column("employee_documents", "reviewed_at")
    op.drop_column("employee_documents", "reviewed_by_sub")
    op.drop_column("employee_documents", "review_comment")
    op.drop_column("employee_documents", "review_status")
    op.drop_column("employee_documents", "value_text")
    op.alter_column(
        "employee_documents",
        "uploaded_by_sub",
        existing_type=sa.Text(),
        nullable=False,
    )
    op.alter_column(
        "employee_documents",
        "size_bytes",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.alter_column(
        "employee_documents",
        "content_type",
        existing_type=sa.Text(),
        nullable=False,
    )
    op.alter_column(
        "employee_documents",
        "storage_key",
        existing_type=sa.Text(),
        nullable=False,
    )
    op.alter_column(
        "employee_documents",
        "original_filename",
        existing_type=sa.Text(),
        nullable=False,
    )
