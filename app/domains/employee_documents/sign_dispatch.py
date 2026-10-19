"""Validate a two-signer Odoo Sign 18 wizard without creating or sending it.

The transport boundary is READ ONLY until the exact send_request() return
contract and idempotent request reconciliation have been checked in staging.
"""
from __future__ import annotations

import os

from sqlalchemy.orm import Session

from app.domains.employee_documents import signing, sign_requests
from app.domains.odoo_sync import staging
from app.integrations.odoo.client import OdooClientError


class DispatchNotReady(ValueError):
    pass


class DispatchUnavailable(RuntimeError):
    pass


def sending_enabled() -> bool:
    # The send feature is deliberately not exposed yet; a disabled flag
    # cannot accidentally start network-side Odoo mail deliveries.
    return os.getenv("ODOO_SIGN_STAGING_SEND_ENABLED", "").strip().lower() in (
        "1", "true", "yes"
    )


def _fields(target, model: str, expected: dict[str, tuple[str, str | None]]) -> dict:
    result = target.fields_get(model)
    for key, (field_type, relation) in expected.items():
        got = result.get(key)
        if not isinstance(got, dict) or got.get("type") != field_type:
            raise DispatchUnavailable(f"Esquema de Odoo Sign distinto al esperado: {model}.{key}.")
        if relation and got.get("relation") != relation:
            raise DispatchUnavailable(f"Relación Odoo Sign distinta a la esperada: {model}.{key}.")
    return result


def _read_one(target, model: str, record_id: int, *, fields: list[str]) -> dict:
    result = target.search_read(
        model, [("id", "=", record_id)], fields=fields, limit=2,
    )
    if len(result) != 1 or result[0].get("id") != record_id:
        raise DispatchNotReady(f"No se pudo verificar el registro de {model} en Odoo staging.")
    return result[0]


def _validated_partner(target, partner_id: int, allowed_addresses: set[str]) -> dict:
    if type(partner_id) is not int or partner_id <= 0:
        raise DispatchNotReady("Los firmantes requieren IDs numéricos de contactos Odoo.")
    row = _read_one(target, "res.partner", partner_id, fields=["id", "email"])
    address = str(row.get("email") or "").strip().casefold()
    if address not in allowed_addresses:
        raise DispatchNotReady("El contacto Odoo no pertenece a los correos ficticios autorizados.")
    return {"id": partner_id, "address": address}


def _staging_signer_emails() -> tuple[str, str]:
    """Two explicitly configured synthetic signer addresses, in role order.

    Production will resolve signers from the candidate and organization's legal
    representative, not from this staging-only fixture configuration.
    """
    configured = [
        part.strip().casefold()
        for part in os.getenv("ODOO_SIGN_TEST_SIGNER_EMAILS", "").split(",")
    ]
    if (len(configured) != 2 or not configured[0].startswith("empleado.")
            or not configured[1].startswith("representante.")
            or not all(part.endswith("@example.invalid") for part in configured)
            or len(set(configured)) != 2):
        raise DispatchUnavailable(
            "Los firmantes ficticios deben configurarse como Empleado y Representante legal, en ese orden."
        )
    if set(configured) != sign_requests._allowed_signer_addresses():
        raise DispatchUnavailable("Los contactos de prueba no están autorizados.")
    return configured[0], configured[1]


def _resolve_staging_partner_ids(target) -> tuple[int, int]:
    """Resolve Odoo contact IDs privately, never require Odoo access in the UI."""
    email_addresses = _staging_signer_emails()
    ids = []
    for email in email_addresses:
        results = target.search_read(
            "res.partner", [("email", "=", email)],
            fields=["id", "email"], limit=2,
        )
        if (len(results) != 1 or
                str(results[0].get("email") or "").strip().casefold() != email or
                type(results[0].get("id")) is not int or results[0]["id"] <= 0):
            raise DispatchNotReady(
                "No se encontró un contacto de prueba único para el rol de firma en Odoo staging."
            )
        ids.append(results[0]["id"])
    if ids[0] == ids[1]:
        raise DispatchNotReady("Los dos roles no pueden utilizar el mismo contacto.")
    return ids[0], ids[1]


def preview_automatic(db: Session, employee_id: str, *, client=None) -> dict:
    """Read-only preview: the HR admin never sees or enters partner IDs."""
    sign_requests._require_fixture(employee_id)
    try:
        target = client or staging.build_staging_client()
        employee_partner_id, representative_partner_id = _resolve_staging_partner_ids(target)
        checked = preview(
            db, employee_id,
            employee_partner_id=employee_partner_id,
            representative_partner_id=representative_partner_id,
            client=target,
        )
        # Unlike the legacy debugging API, do not expose Odoo internal IDs.
        return {
            "validated": checked["validated"],
            "environment": "staging",
            "signing_order": checked["signing_order"],
            "request_created": False,
            "emails_sent": False,
            "note": "Listos los dos contactos ficticios. La solicitud todavía no se ha enviado.",
        }
    except staging.OdooNotConfigured as exc:
        raise DispatchUnavailable("Conexión Odoo staging no configurada.") from exc
    except OdooClientError as exc:
        raise DispatchUnavailable("No se pudieron comprobar los contactos en Odoo staging.") from exc


def build_wizard_values(
    *, template_id: int, employee_partner_id: int, representative_partner_id: int,
    employee_role_id: int, representative_role_id: int, filename: str,
) -> dict:
    """Validated Odoo x2 one2many command payload; pure and deterministic."""
    if not all(
        type(v) is int and v > 0
        for v in (
            template_id, employee_partner_id, representative_partner_id,
            employee_role_id, representative_role_id,
        )
    ):
        raise DispatchNotReady("Identificadores del asistente Odoo Sign inválidos.")
    if employee_partner_id == representative_partner_id or employee_role_id == representative_role_id:
        raise DispatchNotReady("Se requieren contactos y roles diferentes.")
    if (not isinstance(filename, str) or not filename.strip()
            or filename != filename.strip() or len(filename) > 200
            or any(char in filename for char in ("/", "\\", "\n", "\r", "\0"))
            or not filename.lower().endswith(".pdf")):
        raise DispatchNotReady("El nombre del contrato PDF aprobado es inválido.")
    return {
        "filename": filename,
        "template_id": template_id,
        # Odoo Sign 18's wizard does not infer this from signer_ids on create.
        # An unset count remains 0 even with two valid signer rows.
        "signers_count": 2,
        "subject": "ADN360 - Firma de contrato laboral (PRUEBA)",
        "set_sign_order": True,
        "signer_ids": [
            [0, 0, {"partner_id": employee_partner_id,
                    "role_id": employee_role_id, "mail_sent_order": 1}],
            [0, 0, {"partner_id": representative_partner_id,
                    "role_id": representative_role_id, "mail_sent_order": 2}],
        ],
    }


def preview(
    db: Session,
    employee_id: str,
    *,
    employee_partner_id: int,
    representative_partner_id: int,
    client=None,
    _include_wizard: bool = False,
) -> dict:
    """Read-only preflight for exact template, roles, two partners and signing fields."""
    sign_requests._require_fixture(employee_id)
    if type(employee_partner_id) is not int or type(representative_partner_id) is not int:
        raise DispatchNotReady("Selecciona dos contactos numéricos de Odoo.")
    if employee_partner_id <= 0 or representative_partner_id <= 0 or employee_partner_id == representative_partner_id:
        raise DispatchNotReady("Se requieren dos contactos ficticios distintos.")

    document = signing._contract(db, employee_id)
    if not document or document.odoo_sign_status != "PREPARED" or not document.odoo_sign_template_id:
        raise DispatchNotReady("Prepara primero la plantilla del contrato aprobado.")
    if document.review_status != "APPROVED" or not document.storage_key:
        raise DispatchNotReady("El contrato debe estar cargado y aprobado.")
    if document.odoo_sign_source_key != document.storage_key:
        raise DispatchNotReady("La versión del PDF no coincide con la plantilla aprobada.")
    if document.odoo_sign_request_id is not None:
        raise DispatchNotReady("El contrato ya tiene una solicitud de firma vinculada.")
    if getattr(document, "odoo_sign_dispatch_status", "NOT_SENT") not in (None, "NOT_SENT"):
        raise DispatchNotReady("Existe un intento de envío registrado. Reconcílialo antes de continuar.")

    try:
        target = client or staging.build_staging_client()
        _fields(target, "sign.send.request", {
            "template_id": ("many2one", "sign.template"),
            "signer_ids": ("one2many", "sign.send.request.signer"),
            "set_sign_order": ("boolean", None),
            "subject": ("char", None),
            "filename": ("char", None),
            "signers_count": ("integer", None),
        })
        _fields(target, "sign.send.request.signer", {
            "partner_id": ("many2one", "res.partner"),
            "role_id": ("many2one", "sign.item.role"),
            "mail_sent_order": ("integer", None),
        })
        _fields(target, "sign.template", {
            "sign_item_ids": ("one2many", "sign.item"),
        })
        _fields(target, "res.partner", {"email": ("char", None)})
        _fields(target, "sign.item.role", {"name": ("char", None)})
        item_fields = target.fields_get("sign.item")
        role_field = next(
            (name for name in ("responsible_id", "role_id")
             if item_fields.get(name, {}).get("type") == "many2one"
             and item_fields[name].get("relation") == "sign.item.role"),
            None,
        )
        if not role_field:
            raise DispatchUnavailable("No se encontró el campo de responsable de los bloques de firma.")

        template = _read_one(
            target, "sign.template", document.odoo_sign_template_id,
            fields=["id", "sign_item_ids"],
        )
        item_ids = template.get("sign_item_ids") or []
        if not isinstance(item_ids, list) or not item_ids or not all(type(i) is int for i in item_ids):
            raise DispatchNotReady("La plantilla no tiene campos de firma verificables.")
        sign_items = target.search_read(
            "sign.item", [("id", "in", item_ids)],
            fields=["id", role_field], limit=len(item_ids) + 1,
        )
        if len(sign_items) != len(item_ids) or {i.get("id") for i in sign_items} != set(item_ids):
            raise DispatchNotReady("No se pudieron verificar todos los campos de la plantilla.")
        role_ids = {sign_requests._m2o_id(item.get(role_field)) for item in sign_items}
        if None in role_ids or len(role_ids) != 2:
            raise DispatchNotReady("La plantilla requiere únicamente los dos roles de firma configurados.")
        roles = target.search_read(
            "sign.item.role", [("id", "in", sorted(role_ids))],
            fields=["id", "name"], limit=3,
        )
        by_name = {
            sign_requests.canonical_role([item.get("id"), item.get("name")]): item.get("id")
            for item in roles
        }
        if (len(roles) != 2 or set(by_name) != {"employee", "representative"}
                or len(set(by_name.values())) != 2):
            raise DispatchNotReady("Los campos deben pertenecer a Empleado y Representante legal.")

        allowed = sign_requests._allowed_signer_addresses()
        employee = _validated_partner(target, employee_partner_id, allowed)
        representative = _validated_partner(target, representative_partner_id, allowed)
        if employee["address"] == representative["address"]:
            raise DispatchNotReady("Las dos firmas no pueden utilizar el mismo correo.")

        # Odoo 18 requires filename on sign.send.request. Use the approved PDF
        # basename; fall back to a synthetic name for legacy uploads.
        filename = str(getattr(document, "original_filename", "") or "").replace("\\", "/").split("/")[-1].strip()
        if (len(filename) > 200 or not filename.lower().endswith(".pdf")
                or any(char in filename for char in ("\n", "\r", "\0"))):
            filename = "ADN360_contrato_prueba.pdf"

        # Build deterministically but never call create() or send_request().
        _wizard_values = build_wizard_values(
            template_id=document.odoo_sign_template_id,
            employee_partner_id=employee_partner_id,
            representative_partner_id=representative_partner_id,
            employee_role_id=by_name["employee"],
            representative_role_id=by_name["representative"],
            filename=filename,
        )
        assert len(_wizard_values["signer_ids"]) == _wizard_values["signers_count"] == 2
        result = {
            "validated": True,
            "environment": "staging",
            "template_id": document.odoo_sign_template_id,
            "employee_partner_id": employee_partner_id,
            "representative_partner_id": representative_partner_id,
            "signing_order": ["Empleado", "Representante legal"],
            "send_enabled": False,
            "emails_sent": False,
            "request_created": False,
            "note": "Configuración validada; pendiente confirmar el comportamiento de send_request() antes de habilitar el envío.",
            # Deliberately exclude emails, the unsigned PDF, tokens and the
            # internal payload from the HTTP response.
        }
        if _include_wizard:
            result["_wizard_values"] = _wizard_values
        return result
    except staging.OdooNotConfigured as exc:
        raise DispatchUnavailable("Conexión Odoo staging no configurada.") from exc
    except OdooClientError as exc:
        raise DispatchUnavailable("No fue posible consultar Odoo Sign staging.") from exc
    except (DispatchNotReady, DispatchUnavailable):
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise DispatchUnavailable("No se pudo comprobar el asistente Odoo Sign 18.") from exc
