"""add employee signed document storage

Revision ID: 039
Revises: 038
Create Date: 2026-10-02
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "039"
down_revision = "038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "employee_documents",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("employee_id", sa.Text(), nullable=False),
        sa.Column("document_type", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="DRAFT"),
        sa.Column("contract_sync_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column(
            "source_job_candidate_id",
            postgresql.UUID(as_uuid=False),
            nullable=True,
        ),
        sa.Column(
            "current_signed_version_id",
            postgresql.UUID(as_uuid=False),
            nullable=True,
        ),
        sa.Column("created_by_sub", sa.Text(), nullable=False),
        sa.Column("voided_by_sub", sa.Text(), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("void_reason", sa.Text(), nullable=True),
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
            "document_type IN ('CONTRACT', 'ADDENDUM', 'OTHER')",
            name="ck_employee_documents_document_type",
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'PENDING_SIGNATURE', 'SIGNED', 'VOID')",
            name="ck_employee_documents_status",
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["user_profiles.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["contract_sync_id"],
            ["odoo_contract_syncs.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_job_candidate_id"],
            ["job_candidates.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "contract_sync_id",
            name="uq_employee_documents_contract_sync",
        ),
    )
    op.create_index(
        "idx_employee_documents_employee_status",
        "employee_documents",
        ["employee_id", "status"],
        unique=False,
    )

    op.create_table(
        "employee_document_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("artifact_kind", sa.Text(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("template_version", sa.Text(), nullable=False),
        sa.Column("created_by_sub", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "artifact_kind IN ('GENERATED_DOCX', 'REFERENCE_PDF')",
            name="ck_employee_document_artifacts_kind",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["employee_documents.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "storage_key",
            name="uq_employee_document_artifacts_storage_key",
        ),
    )
    op.create_index(
        "idx_employee_document_artifacts_document_created",
        "employee_document_artifacts",
        ["document_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "employee_document_versions",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("uploaded_by_sub", sa.Text(), nullable=False),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "superseded_by_version_id",
            postgresql.UUID(as_uuid=False),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["employee_documents.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["superseded_by_version_id"],
            ["employee_document_versions.id"],
            name="fk_employee_document_versions_superseded_by",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id",
            "version_number",
            name="uq_employee_document_versions_document_version",
        ),
        sa.UniqueConstraint(
            "storage_key",
            name="uq_employee_document_versions_storage_key",
        ),
    )
    op.create_index(
        "idx_employee_document_versions_document_created",
        "employee_document_versions",
        ["document_id", "created_at"],
        unique=False,
    )

    op.create_foreign_key(
        "fk_employee_documents_current_signed_version",
        "employee_documents",
        "employee_document_versions",
        ["current_signed_version_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_employee_documents_current_signed_version",
        "employee_documents",
        type_="foreignkey",
    )
    op.drop_index(
        "idx_employee_document_versions_document_created",
        table_name="employee_document_versions",
    )
    op.drop_table("employee_document_versions")
    op.drop_index(
        "idx_employee_document_artifacts_document_created",
        table_name="employee_document_artifacts",
    )
    op.drop_table("employee_document_artifacts")
    op.drop_index(
        "idx_employee_documents_employee_status",
        table_name="employee_documents",
    )
    op.drop_table("employee_documents")
