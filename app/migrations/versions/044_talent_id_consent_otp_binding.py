"""bind Talent ID biometric consent OTPs to decision and document version

Revision ID: 044
Revises: 043
Create Date: 2026-10-05
"""

from alembic import op
import sqlalchemy as sa


revision = "044"
down_revision = "043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # OTP rows are intentionally short lived. Clearing outstanding challenges
    # avoids inventing a consent decision/document version for pre-fix rows.
    # Signed consent events remain intact; their FK uses ON DELETE SET NULL.
    op.execute("DELETE FROM talent_biometric_consent_otps")
    op.add_column(
        "talent_biometric_consent_otps",
        sa.Column("decision", sa.Text(), nullable=False),
    )
    op.add_column(
        "talent_biometric_consent_otps",
        sa.Column("document_version", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("talent_biometric_consent_otps", "document_version")
    op.drop_column("talent_biometric_consent_otps", "decision")
