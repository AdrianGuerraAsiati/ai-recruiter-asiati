"""add selected applicant Odoo outbox and recruiting SLA

Revision ID: 029
Revises: 028
Create Date: 2026-09-28
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column(
            "response_time_business_days",
            sa.Integer(),
            nullable=False,
            server_default="2",
        ),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "phone_call_count",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "onsite_interview_count",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "offer_wait_days",
            sa.Integer(),
            nullable=False,
            server_default="4",
        ),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "offer_wait_reference",
            sa.Text(),
            nullable=False,
            server_default="AFTER_INTERVIEW",
        ),
    )

    op.create_check_constraint(
        "ck_jobs_response_time_business_days",
        "jobs",
        "response_time_business_days >= 0",
    )
    op.create_check_constraint(
        "ck_jobs_phone_call_count",
        "jobs",
        "phone_call_count >= 0",
    )
    op.create_check_constraint(
        "ck_jobs_onsite_interview_count",
        "jobs",
        "onsite_interview_count >= 0",
    )
    op.create_check_constraint(
        "ck_jobs_offer_wait_days",
        "jobs",
        "offer_wait_days >= 0",
    )
    op.create_check_constraint(
        "ck_jobs_offer_wait_reference",
        "jobs",
        "offer_wait_reference IN ('AFTER_INTERVIEW')",
    )

    op.create_table(
        "odoo_applicant_syncs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            nullable=False,
        ),
        sa.Column(
            "job_candidate_id",
            postgresql.UUID(as_uuid=False),
            nullable=False,
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
        sa.Column("odoo_job_id", sa.Text(), nullable=True),
        sa.Column("odoo_applicant_id", sa.Text(), nullable=True),
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
            name="ck_odoo_applicant_syncs_status",
        ),
        sa.ForeignKeyConstraint(
            ["job_candidate_id"],
            ["job_candidates.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "job_candidate_id",
            name="uq_odoo_applicant_syncs_application",
        ),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_odoo_applicant_syncs_idempotency_key",
        ),
    )
    op.create_index(
        "idx_odoo_applicant_syncs_status_updated",
        "odoo_applicant_syncs",
        ["status", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_odoo_applicant_syncs_status_updated",
        table_name="odoo_applicant_syncs",
    )
    op.drop_table("odoo_applicant_syncs")

    op.drop_constraint("ck_jobs_offer_wait_reference", "jobs", type_="check")
    op.drop_constraint("ck_jobs_offer_wait_days", "jobs", type_="check")
    op.drop_constraint("ck_jobs_onsite_interview_count", "jobs", type_="check")
    op.drop_constraint("ck_jobs_phone_call_count", "jobs", type_="check")
    op.drop_constraint("ck_jobs_response_time_business_days", "jobs", type_="check")
    op.drop_column("jobs", "offer_wait_reference")
    op.drop_column("jobs", "offer_wait_days")
    op.drop_column("jobs", "onsite_interview_count")
    op.drop_column("jobs", "phone_call_count")
    op.drop_column("jobs", "response_time_business_days")
