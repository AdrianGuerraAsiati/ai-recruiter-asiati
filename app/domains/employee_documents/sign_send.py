"""Explicit, one-shot Odoo Sign 18 request dispatch in a neutralized staging DB.

No automated retries: when the RPC result is unknown, reconciliation must
verify the remote correlation subject before linking any request.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.domains.employee_documents import sign_dispatch, sign_requests, signing
from app.domains.odoo_sync import staging
from app.integrations.odoo.client import OdooClientError


class DispatchConflict(ValueError):
    pass


class DispatchOutcomeUnknown(RuntimeError):
    pass


def _correlation(document) -> str:
    # A stable UUID-based identifier, free of applicant personal data.
    return f"ADN360-STAGING-{document.id}"


def _check_correlation_schema(target) -> None:
    fields = target.fields_get("sign.request")
    if fields.get("subject", {}).get("type") != "char":
        raise sign_dispatch.DispatchUnavailable(
            "Odoo Sign no permite reconciliar solicitudes por asunto."
        )
    if fields.get("template_id", {}).get("relation") != "sign.template":
        raise sign_dispatch.DispatchUnavailable("Odoo Sign no expone la plantilla de solicitud.")


def _candidates(target, *, template_id: int, subject: str) -> list[dict]:
    _check_correlation_schema(target)
    found = target.search_read(
        "sign.request",
        [("template_id", "=", template_id), ("subject", "=", subject)],
        fields=["id", "template_id", "subject"],
        limit=3,
    )
    if len(found) > 1:
        raise DispatchConflict("Se detectaron solicitudes duplicadas. Revisión manual requerida.")
    return found


def send(
    db: Session,
    employee_id: str,
    *,
    employee_partner_id: int,
    representative_partner_id: int,
    client=None,
) -> dict:
    if not sign_dispatch.sending_enabled():
        raise sign_dispatch.DispatchUnavailable(
            "El envío automático Odoo Sign staging está deshabilitado."
        )
    sign_requests._require_fixture(employee_id)
    target = client or staging.build_staging_client()
    # Read-only validation of template and both signer partners FIRST.
    preflight = sign_dispatch.preview(
        db, employee_id,
        employee_partner_id=employee_partner_id,
        representative_partner_id=representative_partner_id,
        client=target, _include_wizard=True,
    )
    wizard_values = dict(preflight["_wizard_values"])

    # Commit the persistent one-shot guard before ANY remote writes.
    document = signing._contract(db, employee_id, lock=True)
    if document is not None:
        # A previous preflight populated the SQLAlchemy identity map. Force a
        # fresh SELECT FOR UPDATE after acquiring the row lock; otherwise two
        # concurrent sessions could reuse a stale NOT_SENT value.
        db.refresh(document, with_for_update=True)
    if (document is None or document.odoo_sign_request_id is not None
            or document.odoo_sign_dispatch_status not in (None, "NOT_SENT")
            or document.odoo_sign_template_id != preflight["template_id"]
            or document.odoo_sign_source_key != document.storage_key
            or document.review_status != "APPROVED"):
        raise DispatchConflict("El expediente o su solicitud de firma cambió. Revisa antes de enviar.")
    subject = _correlation(document)
    wizard_values["subject"] = subject
    try:
        if _candidates(target, template_id=document.odoo_sign_template_id, subject=subject):
            raise DispatchConflict("Ya existe una solicitud remota con esta referencia. No reenviar.")
    except OdooClientError as exc:
        raise sign_dispatch.DispatchUnavailable(
            "No se pudo verificar que no exista una solicitud previa en Odoo staging."
        ) from exc

    document.odoo_sign_dispatch_status = "DISPATCHING"
    document.odoo_sign_dispatch_subject = subject
    document.odoo_sign_dispatch_started_at = datetime.now(timezone.utc)
    db.commit()

    # From here on, even a timeout could mean the remote Odoo request exists.
    # Do not issue a second Odoo create/send on an uncertain outcome.
    try:
        wizard_id = target.create("sign.send.request", wizard_values)
        if type(wizard_id) is not int or wizard_id <= 0:
            raise DispatchOutcomeUnknown("Odoo no confirmó el asistente de firma.")
        document = signing._contract(db, employee_id, lock=True)
        document.odoo_sign_dispatch_wizard_id = wizard_id
        db.commit()
        action = target.execute_kw(
            "sign.send.request", "send_request", [[wizard_id]],
        )
        if not isinstance(action, dict):
            raise DispatchOutcomeUnknown("Odoo no devolvió una acción de solicitud verificable.")
        context = action.get("context")
        request_id = context.get("id") if isinstance(context, dict) else None
        if type(request_id) is not int or request_id <= 0:
            # Could happen when Odoo closes an activity instead of opening
            # sign.Document; reconcile safely by subject.
            matches = _candidates(
                target, template_id=preflight["template_id"], subject=subject,
            )
            if len(matches) != 1:
                raise DispatchOutcomeUnknown("Odoo no devolvió una referencia de solicitud única.")
            request_id = matches[0]["id"]
        # Verify the actual request, template, BOTH roles and allowlisted emails.
        sign_requests.track(db, employee_id, request_id=request_id, client=target)
        document = signing._contract(db, employee_id, lock=True)
        document.odoo_sign_dispatch_status = "SENT"
        db.commit()
        return {
            "status": "SENT", "request_id": request_id,
            "emails_delivered": False, "staging_only": True,
            "message": "Solicitud Odoo Sign creada y verificada en staging; entrega de correos no garantizada.",
        }
    except Exception as exc:
        db.rollback()
        document = signing._contract(db, employee_id, lock=True)
        if document and document.odoo_sign_dispatch_status == "DISPATCHING":
            document.odoo_sign_dispatch_status = "UNKNOWN"
            db.commit()
        raise DispatchOutcomeUnknown(
            "Odoo pudo haber creado la solicitud. No reintentar el envío; primero reconciliar."
        ) from exc


def send_automatic(db: Session, employee_id: str, *, client=None) -> dict:
    """Send without exposing Odoo contacts/IDs to Talent Human admin."""
    if not sign_dispatch.sending_enabled():
        raise sign_dispatch.DispatchUnavailable(
            "El envío automático Odoo Sign staging está deshabilitado."
        )
    sign_requests._require_fixture(employee_id)
    try:
        target = client or staging.build_staging_client()
        employee_id_odoo, representative_id_odoo = sign_dispatch._resolve_staging_partner_ids(target)
    except staging.OdooNotConfigured as exc:
        raise sign_dispatch.DispatchUnavailable("Conexión Odoo staging no configurada.") from exc
    except OdooClientError as exc:
        raise sign_dispatch.DispatchUnavailable("No se pudieron verificar los contactos en Odoo staging.") from exc
    return send(
        db, employee_id,
        employee_partner_id=employee_id_odoo,
        representative_partner_id=representative_id_odoo,
        client=target,
    )


def reconcile(db: Session, employee_id: str, *, client=None) -> dict:
    """Read remote state by unique subject. Never send another invitation."""
    sign_requests._require_fixture(employee_id)
    document = signing._contract(db, employee_id, lock=True)
    if not document or document.odoo_sign_dispatch_status not in (
        "DISPATCHING", "UNKNOWN", "SENT",
    ) or not document.odoo_sign_dispatch_subject:
        raise DispatchConflict("No existe un intento de envío pendiente de reconciliación.")
    expected = _correlation(document)
    if document.odoo_sign_dispatch_subject != expected:
        raise DispatchConflict("La referencia del intento no coincide con el expediente.")

    if document.odoo_sign_request_id is not None:
        result = sign_requests.track(db, employee_id, client=client)
        document = signing._contract(db, employee_id, lock=True)
        document.odoo_sign_dispatch_status = "SENT"
        db.commit()
        return {"status": "SENT", "request_id": result["request_id"], "staging_only": True}

    try:
        target = client or staging.build_staging_client()
        matches = _candidates(
            target, template_id=document.odoo_sign_template_id, subject=expected,
        )
        if not matches:
            document.odoo_sign_dispatch_status = "UNKNOWN"
            db.commit()
            return {
                "status": "UNKNOWN", "request_id": None, "staging_only": True,
                "message": "No aparece una solicitud remota. No reintentar automáticamente.",
            }
        request_id = matches[0]["id"]
        sign_requests.track(db, employee_id, request_id=request_id, client=target)
        document = signing._contract(db, employee_id, lock=True)
        document.odoo_sign_dispatch_status = "SENT"
        db.commit()
        return {"status": "SENT", "request_id": request_id, "staging_only": True}
    except (sign_requests.SignTrackingUnavailable, sign_requests.SignTrackingConflict,
            DispatchConflict, OdooClientError, staging.OdooNotConfigured) as exc:
        db.rollback()
        raise DispatchOutcomeUnknown(
            "No fue posible reconciliar de forma única la solicitud. Revisión manual requerida."
        ) from exc
