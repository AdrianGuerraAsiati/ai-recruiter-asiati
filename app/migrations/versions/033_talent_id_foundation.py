"""add Talent ID attendance foundation

Revision ID: 033
Revises: 032
Create Date: 2026-10-01
"""

from alembic import op
import sqlalchemy as sa


revision = "033"
down_revision = "032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "talent_sites",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("code", sa.Text(), nullable=True),
        sa.Column(
            "timezone",
            sa.Text(),
            nullable=False,
            server_default="America/Bogota",
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_talent_sites_code"),
    )
    op.create_index("idx_talent_sites_active", "talent_sites", ["active"])

    op.create_table(
        "talent_work_schedules",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column(
            "tolerance_minutes",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_talent_work_schedules_active",
        "talent_work_schedules",
        ["active"],
    )

    op.create_table(
        "talent_employee_attendance_settings",
        sa.Column("employee_id", sa.Text(), nullable=False),
        sa.Column("site_id", sa.Text(), nullable=True),
        sa.Column("schedule_id", sa.Text(), nullable=True),
        sa.Column(
            "attendance_eligible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["user_profiles.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["site_id"],
            ["talent_sites.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["schedule_id"],
            ["talent_work_schedules.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("employee_id"),
    )
    op.create_index(
        "ix_talent_employee_attendance_settings_site_id",
        "talent_employee_attendance_settings",
        ["site_id"],
    )
    op.create_index(
        "ix_talent_employee_attendance_settings_schedule_id",
        "talent_employee_attendance_settings",
        ["schedule_id"],
    )

    op.create_table(
        "talent_kiosk_devices",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("site_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["site_id"],
            ["talent_sites.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_talent_kiosk_devices_site_active",
        "talent_kiosk_devices",
        ["site_id", "active"],
    )

    op.create_table(
        "talent_biometric_enrollments",
        sa.Column("employee_id", sa.Text(), nullable=False),
        sa.Column(
            "provider",
            sa.Text(),
            nullable=False,
            server_default="AWS_REKOGNITION",
        ),
        sa.Column("provider_user_id", sa.Text(), nullable=False),
        sa.Column("face_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "enrolled_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["user_profiles.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("employee_id"),
        sa.UniqueConstraint(
            "provider_user_id",
            name="uq_talent_biometric_enrollments_provider_user_id",
        ),
    )

    op.create_table(
        "talent_attendance_events",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("employee_id", sa.Text(), nullable=False),
        sa.Column("site_id", sa.Text(), nullable=False),
        sa.Column("device_id", sa.Text(), nullable=True),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("recognition_confidence", sa.Float(), nullable=True),
        sa.CheckConstraint(
            "event_type IN ('CHECK_IN', 'CHECK_OUT')",
            name="ck_talent_attendance_events_event_type",
        ),
        sa.CheckConstraint(
            "method IN ('FACE', 'PIN', 'QR', 'MANUAL')",
            name="ck_talent_attendance_events_method",
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["user_profiles.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["site_id"],
            ["talent_sites.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["talent_kiosk_devices.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_talent_attendance_events_idempotency_key",
        ),
    )
    op.create_index(
        "idx_talent_attendance_events_employee_date",
        "talent_attendance_events",
        ["employee_id", "occurred_at"],
    )
    op.create_index(
        "idx_talent_attendance_events_site_date",
        "talent_attendance_events",
        ["site_id", "occurred_at"],
    )

    op.execute(
        sa.text(
            """
            INSERT INTO permissions (code, description)
            VALUES
                ('talent_id.read', 'Consultar sedes, horarios, dispositivos y asistencia.'),
                ('talent_id.manage', 'Administrar Talent ID, asistencia y dispositivos.')
            ON CONFLICT (code) DO NOTHING
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO role_permissions (role_code, permission_code)
            VALUES
                ('SUPER_ADMIN', 'talent_id.read'),
                ('SUPER_ADMIN', 'talent_id.manage'),
                ('ADMIN', 'talent_id.read'),
                ('ADMIN', 'talent_id.manage')
            ON CONFLICT (role_code, permission_code) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM role_permissions
            WHERE permission_code IN ('talent_id.read', 'talent_id.manage')
            """
        )
    )
    op.execute(
        sa.text(
            """
            DELETE FROM permissions
            WHERE code IN ('talent_id.read', 'talent_id.manage')
            """
        )
    )

    op.drop_index(
        "idx_talent_attendance_events_site_date",
        table_name="talent_attendance_events",
    )
    op.drop_index(
        "idx_talent_attendance_events_employee_date",
        table_name="talent_attendance_events",
    )
    op.drop_table("talent_attendance_events")
    op.drop_table("talent_biometric_enrollments")
    op.drop_index(
        "idx_talent_kiosk_devices_site_active",
        table_name="talent_kiosk_devices",
    )
    op.drop_table("talent_kiosk_devices")
    op.drop_index(
        "ix_talent_employee_attendance_settings_schedule_id",
        table_name="talent_employee_attendance_settings",
    )
    op.drop_index(
        "ix_talent_employee_attendance_settings_site_id",
        table_name="talent_employee_attendance_settings",
    )
    op.drop_table("talent_employee_attendance_settings")
    op.drop_index(
        "idx_talent_work_schedules_active",
        table_name="talent_work_schedules",
    )
    op.drop_table("talent_work_schedules")
    op.drop_index("idx_talent_sites_active", table_name="talent_sites")
    op.drop_table("talent_sites")
