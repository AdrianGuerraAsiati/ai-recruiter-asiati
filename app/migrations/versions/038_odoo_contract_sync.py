"""add Odoo employee contract sync outbox

Revision ID: 038
Revises: 037
Create Date: 2026-10-02
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "038"
down_revision = "037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "odoo_contract_syncs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            nullable=False,
        ),
        sa.Column("employee_id", sa.Text(), nullable=False),
        sa.Column(
            "source_job_candidate_id",
            postgresql.UUID(as_uuid=False),
            nullable=True,
        ),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("odoo_record_id", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'SYNCED', 'FAILED')",
            name="ck_odoo_contract_syncs_status",
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["user_profiles.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_job_candidate_id"],
            ["job_candidates.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "employee_id",
            name="uq_odoo_contract_syncs_employee",
        ),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_odoo_contract_syncs_idempotency_key",
        ),
    )
    op.create_index(
        "idx_odoo_contract_syncs_status_updated",
        "odoo_contract_syncs",
        ["status", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_odoo_contract_syncs_status_updated",
        table_name="odoo_contract_syncs",
    )
    op.drop_table("odoo_contract_syncs")
