"""Odoo Sign uses the existing production Odoo connection, never the test database.

All new remote references belong to production. Old staging identifiers are
explicitly blocked, since numeric IDs are not portable between databases.
"""
from __future__ import annotations

import json
import os
import re
from urllib.parse import urlparse

from app.config import get_odoo_settings
from app.domains.odoo_sync import integration
from app.domains.employee_documents.models import ApplicationContract
from app.models import UserProfile


class ProductionSignUnavailable(RuntimeError):
    pass


def settings():
    configured = get_odoo_settings()
    url = urlparse(configured.base_url)
    test_host = urlparse(os.getenv("ODOO_STAGING_BASE_URL", "")).hostname
    if (
        not configured.enabled or not configured.configured
        or url.scheme != "https" or not url.hostname
        or url.hostname.endswith(".dev.odoo.com")
        or "test160526" in url.hostname.lower()
        or url.username or url.password or url.query or url.fragment
        or url.path not in ("", "/")
        or url.port not in (None, 443)
        or (test_host and test_host == url.hostname)
        or (os.getenv("ODOO_STAGING_DATABASE") and
            configured.database == os.getenv("ODOO_STAGING_DATABASE"))
        or (os.getenv("ODOO_STAGING_SECRET_ID") and
            configured.secret_id == os.getenv("ODOO_STAGING_SECRET_ID"))
    ):
        raise ProductionSignUnavailable("La conexión a Odoo Producción no está aislada.")
    return configured


def enabled():
    return os.getenv("ODOO_SIGN_PRODUCTION_ENABLED", "false").strip().lower() in (
        "1", "true", "yes"
    )


def client():
    settings()
    if not enabled():
        raise ProductionSignUnavailable("La firma productiva no está habilitada.")
    return integration.build_odoo_client()


def base_url():
    return settings().base_url.rstrip("/")


def assert_origin(document, *, new=False):
    if document is None:
        raise ProductionSignUnavailable("No existe el expediente contractual.")
    origin = getattr(document, "odoo_sign_environment", None)
    remote = (
        getattr(document, "odoo_sign_template_id", None)
        or getattr(document, "odoo_sign_request_id", None)
        or getattr(document, "odoo_sign_status", None) in ("PREPARED", "PREPARING")
    )
    if origin == "production":
        return
    if new and origin is None and not remote:
        return
    raise ProductionSignUnavailable(
        "El contrato tiene referencias a Odoo Test. No se reutilizan IDs en Producción."
    )


def _address(email):
    value = str(email or "").strip().casefold()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value) or value.endswith(".invalid"):
        raise ProductionSignUnavailable("El firmante no tiene un correo real válido.")
    return value


def signers(db, document):
    """Require explicit authorized legal representative per bound Odoo company."""
    assert_origin(document)
    binding = db.query(ApplicationContract).filter(
        ApplicationContract.document_id == document.id
    ).one_or_none()
    if (
        not binding or binding.employee_id != document.employee_id
        or binding.source_storage_key != document.storage_key
        or binding.odoo_company_id <= 0
        or document.review_status != "APPROVED"
    ):
        raise ProductionSignUnavailable(
            "El contrato debe estar aprobado y vinculado a la empresa Odoo correcta."
        )
    employee = db.query(UserProfile).filter(
        UserProfile.id == document.employee_id
    ).one_or_none()
    email = _address(employee.email if employee else "")
    try:
        mapping = json.loads(os.getenv("ODOO_SIGN_LEGAL_REPRESENTATIVES_JSON", "{}"))
    except (TypeError, ValueError) as exc:
        raise ProductionSignUnavailable("Configuración de representantes legales inválida.") from exc
    if not isinstance(mapping, dict):
        raise ProductionSignUnavailable("Configuración de representantes legales inválida.")
    representative = _address(mapping.get(str(binding.odoo_company_id)))
    if representative == email:
        raise ProductionSignUnavailable("El empleado y el representante deben ser distintos.")
    return email, representative
