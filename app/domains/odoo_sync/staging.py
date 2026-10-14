"""Dedicated Odoo staging connection; never silently fall back to production."""
from __future__ import annotations

import os
from urllib.parse import urlparse

from app.config import OdooSettings, get_odoo_settings
from app.domains.odoo_sync.integration import OdooNotConfigured, build_odoo_client


def staging_settings() -> OdooSettings:
    url = os.getenv("ODOO_STAGING_BASE_URL", "").strip().rstrip("/")
    database = os.getenv("ODOO_STAGING_DATABASE", "").strip()
    username = os.getenv("ODOO_STAGING_USERNAME", "").strip()
    secret_id = os.getenv("ODOO_STAGING_SECRET_ID", "").strip()
    production = get_odoo_settings()
    if not all((url, database, username, secret_id)):
        raise OdooNotConfigured("Odoo staging requires separate URL, database, username and secret.")
    staging_host = urlparse(url).hostname or ""
    prod_host = urlparse(production.base_url).hostname or ""
    if urlparse(url).scheme != "https":
        raise OdooNotConfigured("Odoo staging must use HTTPS.")
    if staging_host == prod_host and prod_host:
        raise OdooNotConfigured("Staging cannot reuse the production Odoo host.")
    if database == production.database and production.database:
        raise OdooNotConfigured("Staging cannot reuse the production Odoo database.")
    if secret_id == production.secret_id:
        raise OdooNotConfigured("Staging cannot reuse the production API secret.")
    if "/prod/" in secret_id.lower():
        raise OdooNotConfigured("A production-named secret is not permitted for staging.")
    return OdooSettings(
        enabled=True, base_url=url, database=database, username=username,
        secret_id=secret_id,
        request_timeout_seconds=production.request_timeout_seconds,
    )


def build_staging_client(*, secret_store=None, proxy_factory=None):
    """Build an isolated XML-RPC client from dedicated staging credentials."""
    return build_odoo_client(
        settings=staging_settings(), secret_store=secret_store,
        proxy_factory=proxy_factory,
    )
