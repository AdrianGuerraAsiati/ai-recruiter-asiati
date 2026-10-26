"""Bind employment contracts to one application and one Odoo company.

Revision ID: 059
Revises: 058
Create Date: 2026-10-26

Additive migration: historical employee_documents remain unchanged and are
NOT automatically associated with an application. An operator must verify
legacy dossiers individually before using them for a new hire.
"""
from alembic import op
import sqlalchemy as sa

revision = "059"
down_revision = "058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "application_contracts",
        sa.Column("application_id", sa.Uuid(as_uuid=False), sa.ForeignKey("job_candidates.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("employee_id", sa.Text(), sa.ForeignKey("user_profiles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("document_id", sa.Text(), sa.ForeignKey("employee_documents.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("odoo_company_id", sa.Integer(), nullable=False),
        sa.Column("source_storage_key", sa.Text(), nullable=False),
        sa.Column("bound_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("document_id", name="uq_application_contracts_document"),
        sa.CheckConstraint("odoo_company_id > 0", name="ck_application_contracts_company_positive"),
    )
    op.create_index("idx_application_contracts_employee", "application_contracts", ["employee_id"])


def downgrade() -> None:
    op.drop_index("idx_application_contracts_employee", table_name="application_contracts")
    op.drop_table("application_contracts")
