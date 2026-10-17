"""Track Odoo Sign requests for staged contract E2E checks.

Revision ID: 055
Revises: 054
Create Date: 2026-10-17
"""
from alembic import op
import sqlalchemy as sa

revision = "055"
down_revision = "054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("employee_documents", sa.Column("odoo_sign_request_id", sa.Integer(), nullable=True))
    op.add_column("employee_documents", sa.Column(
        "odoo_sign_request_status", sa.Text(), nullable=False, server_default="UNLINKED",
    ))
    op.add_column("employee_documents", sa.Column("odoo_sign_employee_state", sa.Text(), nullable=True))
    op.add_column("employee_documents", sa.Column("odoo_sign_representative_state", sa.Text(), nullable=True))
    op.add_column("employee_documents", sa.Column("odoo_sign_checked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("employee_documents", sa.Column("odoo_sign_completed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_unique_constraint(
        "uq_employee_documents_odoo_sign_request_id", "employee_documents", ["odoo_sign_request_id"]
    )
    op.create_check_constraint(
        "ck_employee_documents_odoo_sign_request_status",
        "employee_documents",
        "odoo_sign_request_status IN "
        "('UNLINKED', 'PENDING_SIGNATURE', 'PARTIALLY_SIGNED', 'SIGNED', 'CANCELLED', 'EXPIRED')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_employee_documents_odoo_sign_request_status", "employee_documents", type_="check",
    )
    op.drop_constraint("uq_employee_documents_odoo_sign_request_id", "employee_documents", type_="unique")
    for column in (
        "odoo_sign_completed_at",
        "odoo_sign_checked_at",
        "odoo_sign_representative_state",
        "odoo_sign_employee_state",
        "odoo_sign_request_status",
        "odoo_sign_request_id",
    ):
        op.drop_column("employee_documents", column)
