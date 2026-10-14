"""Read-only preflight for the dedicated Talent termination E2E environment.

This script makes NO network requests and NO writes to Talent, Odoo or Cognito.
It prints readiness booleans, never credentials, names, emails or database URLs.
"""
from __future__ import annotations

import os

from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import ArgumentError


EXPECTED_DB = "talent_e2e_terminations"


def checks() -> dict[str, bool]:
    production_pool = os.getenv("COGNITO_USER_POOL_ID", "").strip()
    staging_pool = os.getenv("COGNITO_STAGING_USER_POOL_ID", "").strip()
    try:
        parsed = make_url(os.getenv("DATABASE_URL", ""))
        isolated_db = (
            parsed.get_backend_name() == "postgresql"
            and parsed.database == EXPECTED_DB
        )
    except (ArgumentError, ValueError, AttributeError):
        isolated_db = False

    try:
        from app.domains.odoo_sync.staging import staging_settings
        from urllib.parse import urlparse

        settings = staging_settings()
        odoo_isolated = (
            urlparse(settings.base_url).hostname
            == "asiati-test160526-39554181.dev.odoo.com"
            and settings.database == "asiati-test160526-39554181"
        )
    except (RuntimeError, ValueError, AttributeError):
        odoo_isolated = False

    return {
        "app_environment_is_staging": os.getenv("APP_ENV", "").lower() == "staging",
        "talent_database_is_dedicated_postgres": isolated_db,
        "odoo_target_is_expected_staging": odoo_isolated,
        "cognito_uses_separate_pool": bool(
            production_pool and staging_pool and staging_pool != production_pool
        ),
        "termination_execution_opted_in": (
            os.getenv("EMPLOYEE_TERMINATION_EXECUTION_ENABLED") == "true"
        ),
    }


def main():
    readiness = checks()
    for key, ready in readiness.items():
        print(f"{key}: {'OK' if ready else 'NOT_READY'}")
    # Exit nonzero when run in real stage; allow production to display NOT_READY.
    if not all(readiness.values()):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
