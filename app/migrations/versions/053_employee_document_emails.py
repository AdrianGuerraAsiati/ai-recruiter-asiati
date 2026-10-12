"""add durable employee welcome and document request email

Revision ID: 053
Revises: 052
Create Date: 2026-10-12
"""

import sqlalchemy as sa
from alembic import op

revision = "053"
down_revision = "052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "employee_document_emails",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("employee_id", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False, server_default="WELCOME_DOCUMENTS"),
        sa.Column("status", sa.Text(), nullable=False, server_default="PENDING"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["employee_id"], ["user_profiles.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("employee_id", "kind", name="uq_employee_document_emails_employee_kind"),
        sa.CheckConstraint(
            "status IN ('PENDING', 'SENDING', 'SENT', 'FAILED')",
            name="ck_employee_document_emails_status",
        ),
    )
    op.create_index("idx_employee_document_emails_status", "employee_document_emails", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_employee_document_emails_status", table_name="employee_document_emails")
    op.drop_table("employee_document_emails")
