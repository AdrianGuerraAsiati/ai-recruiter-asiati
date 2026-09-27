"""separate recruitment read and write permissions

Revision ID: 026
Revises: 025
Create Date: 2026-09-27
"""

from alembic import op
import sqlalchemy as sa


revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


NEW_PERMISSIONS = (
    (
        "candidates.manage",
        "Crear, asignar y actualizar candidatos y postulaciones.",
    ),
    (
        "ranking.recalculate",
        "Recalcular rankings de candidatos.",
    ),
)


def upgrade() -> None:
    permissions = sa.table(
        "permissions",
        sa.column("code", sa.Text()),
        sa.column("description", sa.Text()),
    )
    role_permissions = sa.table(
        "role_permissions",
        sa.column("role_code", sa.Text()),
        sa.column("permission_code", sa.Text()),
    )

    op.bulk_insert(
        permissions,
        [
            {"code": code, "description": description}
            for code, description in NEW_PERMISSIONS
        ],
    )
    op.bulk_insert(
        role_permissions,
        [
            {"role_code": role_code, "permission_code": permission_code}
            for role_code in ("SUPER_ADMIN", "ADMIN")
            for permission_code, _description in NEW_PERMISSIONS
        ],
    )


def downgrade() -> None:
    codes = tuple(code for code, _description in NEW_PERMISSIONS)
    op.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_code IN "
            "(:candidate_manage, :ranking_recalculate)"
        ).bindparams(
            candidate_manage=codes[0],
            ranking_recalculate=codes[1],
        )
    )
    op.execute(
        sa.text(
            "DELETE FROM permissions WHERE code IN "
            "(:candidate_manage, :ranking_recalculate)"
        ).bindparams(
            candidate_manage=codes[0],
            ranking_recalculate=codes[1],
        )
    )
