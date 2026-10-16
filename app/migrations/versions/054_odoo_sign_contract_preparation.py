"""Track manual preparation of employment contracts in Odoo Sign (staging only).

Revision ID: 054
Revises: 053
Create Date: 2026-10-16
"""

from alembic import op
import sqlalchemy as sa

revision = "054"
down_revision = "053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("employee_documents", sa.Column("odoo_sign_template_id", sa.Integer(), nullable=True))
    op.add_column("employee_documents", sa.Column("odoo_sign_attachment_id", sa.Integer(), nullable=True))
    op.add_column("employee_documents", sa.Column("odoo_sign_source_key", sa.Text(), nullable=True))
    op.add_column(
        "employee_documents",
        sa.Column("odoo_sign_status", sa.Text(), nullable=False, server_default="NOT_PREPARED"),
    )
    op.add_column("employee_documents", sa.Column("odoo_sign_prepared_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        "ck_employee_documents_odoo_sign_status",
        "employee_documents",
        "odoo_sign_status IN ('NOT_PREPARED', 'PREPARING', 'PREPARED', 'FAILED')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_employee_documents_odoo_sign_status", "employee_documents", type_="check")
    for column in (
        "odoo_sign_prepared_at",
        "odoo_sign_status",
        "odoo_sign_source_key",
        "odoo_sign_attachment_id",
        "odoo_sign_template_id",
    ):
        op.drop_column("employee_documents", column)
