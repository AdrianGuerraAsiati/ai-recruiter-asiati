"""collapse SUPER_ADMIN into ADMIN

Revision ID: 034
Revises: 033
Create Date: 2026-10-01
"""

from alembic import op
import sqlalchemy as sa


revision = "034"
down_revision = "033"
branch_labels = None
depends_on = None


ADMIN_EMAILS = (
    "sistemas@asiati.com.co",
    "talentohumano@asiati.com.co",
)


def upgrade() -> None:
    # ADMIN becomes the single privileged role and receives every registered
    # system permission, including integrations and private employee scores.
    op.execute(
        sa.text(
            """
            INSERT INTO role_permissions (role_code, permission_code)
            SELECT 'ADMIN', p.code
            FROM permissions AS p
            WHERE NOT EXISTS (
                SELECT 1
                FROM role_permissions AS rp
                WHERE rp.role_code = 'ADMIN'
                  AND rp.permission_code = p.code
            )
            """
        )
    )

    # Preserve access for every legacy SUPER_ADMIN by converting the assignment
    # to ADMIN before the old role is removed.
    op.execute(
        sa.text(
            """
            INSERT INTO user_roles (user_id, role_code, assigned_by_sub, assigned_at)
            SELECT
                legacy.user_id,
                'ADMIN',
                COALESCE(legacy.assigned_by_sub, 'migration:034'),
                legacy.assigned_at
            FROM user_roles AS legacy
            WHERE legacy.role_code = 'SUPER_ADMIN'
              AND NOT EXISTS (
                  SELECT 1
                  FROM user_roles AS current_role
                  WHERE current_role.user_id = legacy.user_id
                    AND current_role.role_code = 'ADMIN'
              )
            """
        )
    )

    # These two corporate accounts are the explicit administrative bootstrap
    # identities. If their internal profiles already exist, make the role exact.
    op.execute(
        sa.text(
            """
            DELETE FROM user_roles
            WHERE user_id IN (
                SELECT id
                FROM user_profiles
                WHERE lower(email) IN (:systems_email, :hr_email)
            )
            """
        ).bindparams(
            systems_email=ADMIN_EMAILS[0],
            hr_email=ADMIN_EMAILS[1],
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO user_roles (user_id, role_code, assigned_by_sub, assigned_at)
            SELECT
                profile.id,
                'ADMIN',
                'migration:034',
                CURRENT_TIMESTAMP
            FROM user_profiles AS profile
            WHERE lower(profile.email) IN (:systems_email, :hr_email)
            """
        ).bindparams(
            systems_email=ADMIN_EMAILS[0],
            hr_email=ADMIN_EMAILS[1],
        )
    )

    op.execute(sa.text("DELETE FROM user_roles WHERE role_code = 'SUPER_ADMIN'"))
    op.execute(
        sa.text("DELETE FROM role_permissions WHERE role_code = 'SUPER_ADMIN'")
    )
    op.execute(sa.text("DELETE FROM roles WHERE code = 'SUPER_ADMIN'"))
    op.execute(
        sa.text(
            """
            UPDATE roles
            SET name = 'Administrador',
                description = 'Administracion completa del sistema, reclutamiento, empleados, integraciones y capacitacion.'
            WHERE code = 'ADMIN'
            """
        )
    )


def downgrade() -> None:
    roles = sa.table(
        "roles",
        sa.column("code", sa.Text()),
        sa.column("name", sa.Text()),
        sa.column("description", sa.Text()),
    )
    op.bulk_insert(
        roles,
        [
            {
                "code": "SUPER_ADMIN",
                "name": "Super administrador",
                "description": "Acceso total, incluidas las funciones privadas de Direccion.",
            }
        ],
    )
    op.execute(
        sa.text(
            """
            INSERT INTO role_permissions (role_code, permission_code)
            SELECT 'SUPER_ADMIN', p.code
            FROM permissions AS p
            WHERE NOT EXISTS (
                SELECT 1
                FROM role_permissions AS rp
                WHERE rp.role_code = 'SUPER_ADMIN'
                  AND rp.permission_code = p.code
            )
            """
        )
    )
