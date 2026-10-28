"""Select the Odoo Sign environment explicitly, without staging-to-production fallback."""
import os
from urllib.parse import urlparse
from app.config import get_odoo_settings
from app.domains.odoo_sync import integration, staging

class OdooSignTargetError(RuntimeError):
    pass

def environment():
    name = os.getenv("ODOO_SIGN_TARGET", "staging").strip().lower()
    if name not in ("production", "staging"):
        raise OdooSignTargetError("Invalid Odoo Sign target")
    return name

def production():
    return environment() == "production"

def enabled(action):
    if action not in ("prepare", "track", "send", "archive"):
        raise OdooSignTargetError("Unknown Odoo Sign action")
    name = "ODOO_SIGN_" + ("PRODUCTION_" if production() else "STAGING_") + action.upper() + "_ENABLED"
    enabled_flag = os.getenv(name, "false").lower() in ("1", "true", "yes")
    return enabled_flag and (not production() or os.getenv("ODOO_SIGN_PRODUCTION_ENABLED", "false").lower() in ("1", "true", "yes"))

def production_settings():
    settings = get_odoo_settings()
    url = urlparse(settings.base_url)
    staging_host = urlparse(os.getenv("ODOO_STAGING_BASE_URL", "")).hostname
    if (not settings.enabled or not settings.configured or url.scheme != "https"
        or not url.hostname or url.hostname.endswith(".dev.odoo.com")
        or "test160526" in url.hostname or url.username or url.password
        or url.query or url.fragment or url.path not in ("", "/")
        or (staging_host and staging_host == url.hostname)
        or (os.getenv("ODOO_STAGING_DATABASE") and settings.database == os.getenv("ODOO_STAGING_DATABASE"))
        or (os.getenv("ODOO_STAGING_SECRET_ID") and settings.secret_id == os.getenv("ODOO_STAGING_SECRET_ID"))):
        raise OdooSignTargetError("Production Odoo connection is not safely separated from staging")
    return settings

def client():
    if production():
        production_settings()
        if os.getenv("ODOO_SIGN_PRODUCTION_ENABLED", "false").lower() not in ("1", "true", "yes"):
            raise OdooSignTargetError("Production Odoo Sign is disabled")
        return integration.build_odoo_client()
    return staging.build_staging_client()

def base_url():
    if production():
        return production_settings().base_url.rstrip("/")
    return staging.staging_settings().base_url.rstrip("/")

def assert_document_origin(document, allow_new=False):
    if document is None:
        raise OdooSignTargetError("Missing contract dossier")
    origin = getattr(document, "odoo_sign_environment", None)
    prior = bool(getattr(document, "odoo_sign_template_id", None) or
                 getattr(document, "odoo_sign_request_id", None) or
                 getattr(document, "odoo_sign_status", None) in ("PREPARING", "PREPARED"))
    if allow_new and not prior and not origin:
        return
    if (origin or "staging") != environment():
        raise OdooSignTargetError("Contract was prepared in another Odoo database; never reuse its remote IDs")
