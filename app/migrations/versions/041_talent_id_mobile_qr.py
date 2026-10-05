"""add Talent ID linked mobile QR attendance

Revision ID: 041
Revises: 040
Create Date: 2026-10-05
"""

from alembic import op
import sqlalchemy as sa


revision = "041"
down_revision = "040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "talent_mobile_device_link_otps",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("employee_id", sa.Text(), nullable=False),
        sa.Column("otp_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "attempts >= 0 AND max_attempts > 0",
            name="ck_talent_mobile_device_link_otp_attempts",
        ),
        sa.ForeignKeyConstraint(["employee_id"], ["user_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_talent_mobile_device_link_otps_employee_created",
        "talent_mobile_device_link_otps",
        ["employee_id", "created_at"],
    )

    op.create_table(
        "talent_mobile_devices",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("employee_id", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("public_key_jwk", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["employee_id"], ["user_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_talent_mobile_devices_employee_active",
        "talent_mobile_devices",
        ["employee_id", "active"],
    )

    op.create_table(
        "talent_mobile_qr_challenges",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("employee_id", sa.Text(), nullable=False),
        sa.Column("mobile_device_id", sa.Text(), nullable=False),
        sa.Column("nonce_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("attempts >= 0", name="ck_talent_mobile_qr_challenge_attempts"),
        sa.ForeignKeyConstraint(["employee_id"], ["user_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["mobile_device_id"], ["talent_mobile_devices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_talent_mobile_qr_challenges_device_created",
        "talent_mobile_qr_challenges",
        ["mobile_device_id", "created_at"],
    )

    op.create_table(
        "talent_mobile_qr_tokens",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("employee_id", sa.Text(), nullable=False),
        sa.Column("mobile_device_id", sa.Text(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["employee_id"], ["user_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["mobile_device_id"], ["talent_mobile_devices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_talent_mobile_qr_tokens_hash"),
    )
    op.create_index(
        "idx_talent_mobile_qr_tokens_employee_created",
        "talent_mobile_qr_tokens",
        ["employee_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_talent_mobile_qr_tokens_employee_created",
        table_name="talent_mobile_qr_tokens",
    )
    op.drop_table("talent_mobile_qr_tokens")
    op.drop_index(
        "idx_talent_mobile_qr_challenges_device_created",
        table_name="talent_mobile_qr_challenges",
    )
    op.drop_table("talent_mobile_qr_challenges")
    op.drop_index(
        "idx_talent_mobile_devices_employee_active",
        table_name="talent_mobile_devices",
    )
    op.drop_table("talent_mobile_devices")
    op.drop_index(
        "idx_talent_mobile_device_link_otps_employee_created",
        table_name="talent_mobile_device_link_otps",
    )
    op.drop_table("talent_mobile_device_link_otps")
