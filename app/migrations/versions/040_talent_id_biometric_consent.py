"""add Talent ID biometric consent signatures

Revision ID: 040
Revises: 039
Create Date: 2026-10-05
"""

from alembic import op
import sqlalchemy as sa


revision = "040"
down_revision = "039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "talent_biometric_consent_otps",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("employee_id", sa.Text(), nullable=False),
        sa.Column("otp_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "attempts >= 0 AND max_attempts > 0",
            name="ck_talent_biometric_consent_otp_attempts",
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["user_profiles.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_talent_biometric_consent_otps_employee_created",
        "talent_biometric_consent_otps",
        ["employee_id", "created_at"],
    )

    op.create_table(
        "talent_biometric_consent_events",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("employee_id", sa.Text(), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("document_version", sa.Text(), nullable=False),
        sa.Column("document_sha256", sa.Text(), nullable=False),
        sa.Column("pdf_sha256", sa.Text(), nullable=False),
        sa.Column("signed_pdf", sa.LargeBinary(), nullable=False),
        sa.Column("verified_email", sa.Text(), nullable=False),
        sa.Column("otp_challenge_id", sa.Text(), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column(
            "signed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "decision IN ('AUTHORIZED', 'DENIED', 'REVOKED')",
            name="ck_talent_biometric_consent_events_decision",
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["user_profiles.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["otp_challenge_id"],
            ["talent_biometric_consent_otps.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_talent_biometric_consent_events_employee_signed",
        "talent_biometric_consent_events",
        ["employee_id", "signed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_talent_biometric_consent_events_employee_signed",
        table_name="talent_biometric_consent_events",
    )
    op.drop_table("talent_biometric_consent_events")
    op.drop_index(
        "idx_talent_biometric_consent_otps_employee_created",
        table_name="talent_biometric_consent_otps",
    )
    op.drop_table("talent_biometric_consent_otps")
