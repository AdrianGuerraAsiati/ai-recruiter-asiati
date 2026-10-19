"""Track Odoo Sign completion certificate alongside immutable signed PDF.

Revision ID: 058
Revises: 057
Create Date: 2026-10-19
"""
from alembic import op
import sqlalchemy as sa

revision = "058"
down_revision = "057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("employee_documents", sa.Column("odoo_sign_certificate_storage_key", sa.Text(), nullable=True))
    op.add_column("employee_documents", sa.Column("odoo_sign_certificate_sha256", sa.Text(), nullable=True))
    op.add_column("employee_documents", sa.Column("odoo_sign_certificate_attachment_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    for column in ("odoo_sign_certificate_attachment_id", "odoo_sign_certificate_sha256",
                   "odoo_sign_certificate_storage_key"):
        op.drop_column("employee_documents", column)
