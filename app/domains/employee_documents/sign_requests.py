"""Read and link staging Odoo Sign requests without sending mail or signatures.

Only explicitly allowlisted synthetic employees and signer addresses can be
tracked. No Odoo writes are performed by this module.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.domains.employee_documents import signing
from app.domains.odoo_sync import integration
from app.domains.employee_documents import sign_runtime
from app.integrations.odoo.client import OdooClientError


class SignTrackingUnavailable(RuntimeError):
    pass


class SignTrackingConflict(ValueError):
    pass


ROLE_NAMES = {"employee": "Empleado", "representative": "Representante legal"}
ROLE_ALIASES = {
    "empleado": "employee",
    "employee": "employee",
    "representante legal": "representative",
    "legal representative": "representative",
}


def canonical_role(value) -> str | None:
    """Normalize Odoo's translated role display names; reject unknown roles."""
    return ROLE_ALIASES.get(_m2o_name(value).casefold())

SIGNED_STATES = frozenset({"signed", "completed"})
CANCELLED_STATES = frozenset({"cancel", "canceled", "cancelled", "refused", "rejected"})
EXPIRED_STATES = frozenset({"expired"})


def tracking_enabled():
    return sign_runtime.enabled()


def _require_fixture(employee_id: str):
    """Compatibility name: validates that production Sign is enabled."""
    if not tracking_enabled():
        raise SignTrackingUnavailable("Odoo Sign producción deshabilitado.")


def _m2o_id(value) -> int | None:
    if isinstance(value, (tuple, list)) and value and isinstance(value[0], int):
        return value[0]
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _m2o_name(value) -> str:
    return str(value[1]).strip() if isinstance(value, (tuple, list)) and len(value) > 1 else ""


def _read_remote(target, request_id: int, *, template_id: int, expected: tuple[str, str]) -> dict:
    """Fail closed unless the request is from the exact staged template and two signers."""
    try:
        request_fields = target.fields_get("sign.request")
        item_fields = target.fields_get("sign.request.item")
        required_request = {"id", "template_id", "request_item_ids", "state"}
        required_item = {"id", "role_id", "state", "signer_email"}
        if not required_request.issubset(request_fields) or not required_item.issubset(item_fields):
            raise SignTrackingUnavailable("La estructura de la API de firmas difiere de la esperada.")

        request = target.search_read(
            "sign.request", [("id", "=", request_id)],
            fields=sorted(required_request), limit=1,
        )
        if len(request) != 1 or request[0].get("id") != request_id:
            raise SignTrackingConflict("No existe esa solicitud en Odoo Producción.")
        remote = request[0]
        if _m2o_id(remote.get("template_id")) != template_id:
            raise SignTrackingConflict("La solicitud no corresponde a la plantilla preparada para este empleado.")

        ids = remote.get("request_item_ids") or []
        if not isinstance(ids, list) or len(ids) != 2 or not all(type(i) is int for i in ids):
            raise SignTrackingConflict("La solicitud debe tener exactamente dos firmantes.")
        items = target.search_read(
            "sign.request.item", [("id", "in", ids)],
            fields=sorted(required_item), limit=3,
        )
        if len(items) != 2 or {i.get("id") for i in items} != set(ids):
            raise SignTrackingConflict("No fue posible verificar los dos firmantes.")

        by_role = {canonical_role(item.get("role_id")): item for item in items}
        if len(by_role) != 2 or set(by_role) != {"employee", "representative"}:
            raise SignTrackingConflict("Se requieren los roles Empleado y Representante legal.")
        addresses = {
            role: str(item.get("signer_email") or "").strip().casefold()
            for role, item in by_role.items()
        }
        if addresses != {"employee": expected[0], "representative": expected[1]}:
            raise SignTrackingConflict("Los correos de los firmantes no coinciden con el expediente.")

        states = {
            role: str(item["state"]).casefold() for role, item in by_role.items()
        }
        overall = str(remote.get("state") or "").casefold()
        if overall in CANCELLED_STATES:
            normalized = "CANCELLED"
        elif overall in EXPIRED_STATES:
            normalized = "EXPIRED"
        elif all(s in SIGNED_STATES for s in states.values()) and overall in SIGNED_STATES:
            normalized = "SIGNED"
        elif any(s in SIGNED_STATES for s in states.values()):
            normalized = "PARTIALLY_SIGNED"
        else:
            normalized = "PENDING_SIGNATURE"

        return {"status": normalized, "remote_status": overall, "signers": states}
    except (OdooClientError, SignTrackingUnavailable, SignTrackingConflict):
        raise
    except (TypeError, ValueError, KeyError) as exc:
        raise SignTrackingUnavailable("La respuesta del proveedor de firma no pudo validarse.") from exc


def local_status(db: Session, employee_id: str) -> dict:
    document = signing._contract(db, employee_id)
    if document is None:
        return {"linked": False, "request_id": None, "status": "UNLINKED",
                "employee": None, "representative": None, "checked_at": None,
                "staging_only": False, "sending_available": False, "signed_pdf_archived": False}
    return {
        "linked": document.odoo_sign_request_id is not None,
        "request_id": document.odoo_sign_request_id,
        "status": document.odoo_sign_request_status,
        "employee": document.odoo_sign_employee_state,
        "representative": document.odoo_sign_representative_state,
        "checked_at": document.odoo_sign_checked_at.isoformat() if document.odoo_sign_checked_at else None,
        "staging_only": False,
        "sending_available": False,
        "signed_pdf_archived": bool(document.odoo_sign_signed_storage_key),
    }


def track(db: Session, employee_id: str, *, request_id: int | None = None, client=None) -> dict:
    """Link a manually created staging request or refresh its verified status."""
    _require_fixture(employee_id)
    document = signing._contract(db, employee_id, lock=True)
    if not document or document.odoo_sign_status != "PREPARED" or not document.odoo_sign_template_id:
        raise SignTrackingConflict("Prepara primero el contrato PDF aprobado en Odoo Sign.")
    try:
        sign_runtime.assert_origin(document)
    except sign_runtime.ProductionSignUnavailable as exc:
        raise SignTrackingConflict(str(exc)) from exc
    if document.odoo_sign_source_key != document.storage_key:
        raise SignTrackingConflict("El PDF del expediente difiere del preparado para firma.")
    if document.review_status != "APPROVED":
        raise SignTrackingConflict("El contrato debe continuar aprobado.")

    remote_id = request_id if request_id is not None else document.odoo_sign_request_id
    if not remote_id or type(remote_id) is not int or remote_id <= 0:
        raise SignTrackingConflict("Indica el ID de una solicitud de prueba válida.")
    if document.odoo_sign_request_id is not None and remote_id != document.odoo_sign_request_id:
        raise SignTrackingConflict("El contrato ya está asociado a otra solicitud de firma.")

    try:
        target = client or sign_runtime.client()
        expected = (
            (document.odoo_sign_employee_email, document.odoo_sign_representative_email)
            if document.odoo_sign_employee_email and document.odoo_sign_representative_email
            else sign_runtime.signers(db, document)
        )
        checked = _read_remote(target, remote_id, template_id=document.odoo_sign_template_id, expected=expected)
    except (sign_runtime.ProductionSignUnavailable, integration.OdooNotConfigured, integration.OdooDisabled, OdooClientError) as exc:
        raise SignTrackingUnavailable("No se pudo consultar Odoo Sign Producción.") from exc
    document.odoo_sign_request_id = remote_id
    document.odoo_sign_request_status = checked["status"]
    document.odoo_sign_employee_state = checked["signers"]["employee"]
    document.odoo_sign_representative_state = checked["signers"]["representative"]
    document.odoo_sign_checked_at = datetime.now(timezone.utc)
    if checked["status"] == "SIGNED" and document.odoo_sign_completed_at is None:
        document.odoo_sign_completed_at = datetime.now(timezone.utc)
    db.commit()
    return local_status(db, employee_id)
