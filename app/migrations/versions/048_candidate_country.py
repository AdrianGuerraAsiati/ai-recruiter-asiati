"""persist candidate country and recover historical geography

Revision ID: 048
Revises: 047
Create Date: 2026-10-07
"""

from alembic import op
import sqlalchemy as sa


revision = "048"
down_revision = "047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("candidates", sa.Column("country_code", sa.Text(), nullable=True))

    # 1) Strongest source: surviving application links. Only use candidates whose
    # linked vacancies all agree on one country.
    op.execute(
        """
        WITH inferred AS (
            SELECT
                jc.candidate_id,
                MIN(UPPER(j.country_code)) AS country_code
            FROM job_candidates jc
            JOIN jobs j ON j.id = jc.job_id
            WHERE NULLIF(BTRIM(j.country_code), '') IS NOT NULL
            GROUP BY jc.candidate_id
            HAVING COUNT(DISTINCT UPPER(j.country_code)) = 1
        )
        UPDATE candidates c
        SET country_code = inferred.country_code
        FROM inferred
        WHERE c.id = inferred.candidate_id
          AND c.country_code IS NULL
        """
    )

    # 2) Odoo ingestion survives vacancy deletion because the ingestion event
    # keeps raw provider metadata. Resolve via the current Odoo job mapping.
    op.execute(
        """
        WITH inferred AS (
            SELECT
                e.candidate_id,
                MIN(UPPER(j.country_code)) AS country_code
            FROM candidate_ingestion_events e
            JOIN odoo_job_syncs sync
              ON sync.odoo_record_id = e.raw_metadata ->> 'odoo_job_id'
            JOIN jobs j ON j.id = sync.job_id
            WHERE e.candidate_id IS NOT NULL
              AND NULLIF(BTRIM(j.country_code), '') IS NOT NULL
            GROUP BY e.candidate_id
            HAVING COUNT(DISTINCT UPPER(j.country_code)) = 1
        )
        UPDATE candidates c
        SET country_code = inferred.country_code
        FROM inferred
        WHERE c.id = inferred.candidate_id
          AND c.country_code IS NULL
        """
    )

    # 3) Provider-neutral historical recovery. Deleted jobs set event.job_id to
    # NULL, but raw_metadata.job_title remains. Match only unambiguous titles.
    op.execute(
        """
        WITH inferred AS (
            SELECT
                e.candidate_id,
                MIN(UPPER(j.country_code)) AS country_code
            FROM candidate_ingestion_events e
            JOIN jobs j
              ON LOWER(BTRIM(j.title)) = LOWER(BTRIM(e.raw_metadata ->> 'job_title'))
            WHERE e.candidate_id IS NOT NULL
              AND NULLIF(BTRIM(e.raw_metadata ->> 'job_title'), '') IS NOT NULL
              AND NULLIF(BTRIM(j.country_code), '') IS NOT NULL
            GROUP BY e.candidate_id
            HAVING COUNT(DISTINCT UPPER(j.country_code)) = 1
        )
        UPDATE candidates c
        SET country_code = inferred.country_code
        FROM inferred
        WHERE c.id = inferred.candidate_id
          AND c.country_code IS NULL
        """
    )

    # Rankings are derived from geography. Any ranking built before this
    # backfill must be regenerated against the recovered candidate countries.
    op.execute("DELETE FROM ranking_items")
    op.execute("DELETE FROM rankings")


def downgrade() -> None:
    op.drop_column("candidates", "country_code")
