"""Composition layer for the Odoo external API transport."""

from __future__ import annotations

from app.config import OdooSettings, get_odoo_settings
from app.infrastructure.odoo_secret import OdooSecretStore
from app.integrations.odoo.client import OdooXmlRpcClient


class OdooDisabled(RuntimeError):
    pass


class OdooNotConfigured(RuntimeError):
    pass


def build_odoo_client(
    *,
    settings: OdooSettings | None = None,
    secret_store=None,
    proxy_factory=None,
) -> OdooXmlRpcClient:
    """Resolve non-secret settings + runtime API key into the transport client."""

    current = settings or get_odoo_settings()
    if not current.enabled:
        raise OdooDisabled("Odoo synchronization is disabled.")
    if not current.configured:
        raise OdooNotConfigured("Odoo connection settings are incomplete.")

    store = secret_store or OdooSecretStore(current.secret_id)
    payload = dict(store.read() or {})
    api_key = str(payload.get("api_key") or "").strip()
    if not api_key:
        raise OdooNotConfigured("Odoo API key is not configured.")

    return OdooXmlRpcClient(
        base_url=current.base_url,
        database=current.database,
        username=current.username,
        api_key=api_key,
        request_timeout_seconds=current.request_timeout_seconds,
        proxy_factory=proxy_factory,
    )


def connection_status(
    *,
    settings: OdooSettings | None = None,
    secret_store=None,
) -> dict:
    """Return configuration readiness without exposing secret material."""

    current = settings or get_odoo_settings()
    secret_present = False
    if current.secret_id:
        try:
            store = secret_store or OdooSecretStore(current.secret_id)
            secret_present = bool(str((store.read() or {}).get("api_key") or "").strip())
        except Exception:
            secret_present = False
    return {
        "enabled": current.enabled,
        "configured": current.configured and secret_present,
        "base_url": current.base_url or None,
        "database_configured": bool(current.database),
        "username_configured": bool(current.username),
        "secret_id": current.secret_id or None,
    }
