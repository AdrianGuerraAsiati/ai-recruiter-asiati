"""Signed Odoo Sign artifact metadata (staging guarded).

Revision ID: 056
Revises: 055
Create Date: 2026-10-17
"""
from alembic import op
import sqlalchemy as sa

revision = "056"
down_revision = "055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("employee_documents", sa.Column("odoo_sign_signed_storage_key", sa.Text(), nullable=True))
    op.add_column("employee_documents", sa.Column("odoo_sign_signed_sha256", sa.Text(), nullable=True))
    op.add_column("employee_documents", sa.Column("odoo_sign_signed_attachment_id", sa.Integer(), nullable=True))
    op.add_column("employee_documents", sa.Column(
        "odoo_sign_signed_at", sa.DateTime(timezone=True), nullable=True
    ))


def downgrade() -> None:
    for column in (
        "odoo_sign_signed_at",
        "odoo_sign_signed_attachment_id",
        "odoo_sign_signed_sha256",
        "odoo_sign_signed_storage_key",
    ):
        op.drop_column("employee_documents", column)
