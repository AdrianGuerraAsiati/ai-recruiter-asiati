"""Staging Odoo Sign send attempt and reconciliation state.

Revision ID: 057
Revises: 056
Create Date: 2026-10-17
"""
from alembic import op
import sqlalchemy as sa

revision = "057"
down_revision = "056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("employee_documents", sa.Column(
        "odoo_sign_dispatch_status", sa.Text(), nullable=False,
        server_default="NOT_SENT",
    ))
    op.add_column("employee_documents", sa.Column("odoo_sign_dispatch_subject", sa.Text(), nullable=True))
    op.add_column("employee_documents", sa.Column("odoo_sign_dispatch_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("employee_documents", sa.Column("odoo_sign_dispatch_wizard_id", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_employee_documents_odoo_sign_dispatch_status", "employee_documents",
        "odoo_sign_dispatch_status IN ('NOT_SENT', 'DISPATCHING', 'SENT', 'UNKNOWN')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_employee_documents_odoo_sign_dispatch_status",
                       "employee_documents", type_="check")
    for name in ("odoo_sign_dispatch_wizard_id", "odoo_sign_dispatch_started_at",
                 "odoo_sign_dispatch_subject", "odoo_sign_dispatch_status"):
        op.drop_column("employee_documents", name)
