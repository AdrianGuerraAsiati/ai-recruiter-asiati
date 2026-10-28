"""Preserve staging origins before enabling production Odoo Sign.

Revision ID: 060
Revises: 059
"""
from alembic import op
import sqlalchemy as sa

revision = "060"
down_revision = "059"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("employee_documents", sa.Column("odoo_sign_environment", sa.Text(), nullable=True))
    op.add_column("employee_documents", sa.Column("odoo_sign_employee_email", sa.Text(), nullable=True))
    op.add_column("employee_documents", sa.Column("odoo_sign_representative_email", sa.Text(), nullable=True))
    op.execute("""
        UPDATE employee_documents SET odoo_sign_environment = 'staging'
         WHERE odoo_sign_template_id IS NOT NULL OR odoo_sign_request_id IS NOT NULL
            OR odoo_sign_status IN ('PREPARED', 'PREPARING')
    """)
    op.create_check_constraint(
        "ck_employee_documents_odoo_sign_environment", "employee_documents",
        "odoo_sign_environment IS NULL OR odoo_sign_environment IN ('staging', 'production')",
    )


def downgrade():
    op.drop_constraint("ck_employee_documents_odoo_sign_environment", "employee_documents", type_="check")
    for col in ("odoo_sign_representative_email", "odoo_sign_employee_email", "odoo_sign_environment"):
        op.drop_column("employee_documents", col)
