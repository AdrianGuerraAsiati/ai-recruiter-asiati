"""Place two mandatory signature fields in a visually marked demo PDF in Odoo staging.

No use of legacy positions: detect separate signature boxes in the approved
PDF itself, validate text/geometry, then write only to its own prepared template.
Never creates a sign.request or sends email.
"""
from __future__ import annotations

import fitz
from sqlalchemy.orm import Session

from app.domains.employee_documents import signing, sign_requests
from app.domains.odoo_sync import staging
from app.infrastructure.storage import employee_documents as storage
from app.integrations.odoo.client import OdooClientError


class SignFieldsNotReady(ValueError):
    pass


class SignFieldsUnavailable(RuntimeError):
    pass


def _document(db: Session, employee_id: str, *, lock: bool = False):
    if not signing.staging_enabled() or not signing._test_employee_allowed(employee_id):
        raise SignFieldsUnavailable("Los campos de firma están deshabilitados para este expediente.")
    doc = signing._contract(db, employee_id, lock=lock)
    if (doc is None or doc.odoo_sign_status != "PREPARED"
            or doc.review_status != "APPROVED"
            or not doc.odoo_sign_template_id or not doc.storage_key
            or doc.odoo_sign_source_key != doc.storage_key
            or doc.odoo_sign_request_id is not None
            or doc.odoo_sign_dispatch_status not in (None, "NOT_SENT")):
        raise SignFieldsNotReady(
            "Se necesita una plantilla aprobada y sin solicitud de firma existente."
        )
    # This prototype is restricted to the synthetic, explicitly named demo PDF.
    if doc.original_filename != "ADN360_contrato_ficticio_prueba_Odoo_Sign.pdf":
        raise SignFieldsNotReady(
            "La detección automática solo está validada para el PDF ficticio ADN360."
        )
    return doc


def _positions(pdf: bytes) -> dict[str, dict]:
    """Locate two separate marked signing boxes; reject unrecognized layouts."""
    try:
        with fitz.open(stream=pdf, filetype="pdf") as source:
            if len(source) != 1:
                raise SignFieldsNotReady("El PDF de demostración debe tener una sola página.")
            page = source[0]
            if ("SOLO PRUEBA" not in page.get_text().upper()
                    or "SIN VALIDEZ CONTRACTUAL" not in page.get_text().upper()):
                raise SignFieldsNotReady("El documento no está identificado como ficticio.")
            rectangles = []
            for drawing in page.get_drawings():
                rect = drawing["rect"]
                if ("4 4" in str(drawing.get("dashes") or "")
                        and rect.width >= 180 and 75 <= rect.height <= 150
                        and rect.y0 > page.rect.height * 0.4):
                    rectangles.append(rect)
            if len(rectangles) != 2 or abs(rectangles[0].y0 - rectangles[1].y0) > 8:
                raise SignFieldsNotReady("No se encontraron exactamente dos recuadros de firma.")
            found = {}
            for area in rectangles:
                label_text = page.get_textbox(area).casefold()
                if "representante legal" in label_text:
                    key = "representative"
                elif "empleado" in label_text:
                    key = "employee"
                else:
                    raise SignFieldsNotReady("No se identificó el rol dentro del recuadro.")
                if key in found:
                    raise SignFieldsNotReady("La plantilla tiene roles de firma duplicados.")
                field_rect = fitz.Rect(area.x0 + 12, area.y0 + 44,
                                       area.x1 - 12, area.y0 + 80)
                if not area.contains(field_rect):
                    raise SignFieldsNotReady("El campo de firma no cabe en el recuadro.")
                for block in page.get_text("dict").get("blocks", []):
                    if block.get("type") != 0:
                        continue
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            if field_rect.intersects(fitz.Rect(span["bbox"])):
                                raise SignFieldsNotReady(
                                    "Una zona de firma se superpone con el texto del PDF."
                                )
                found[key] = {
                    "page": 1,
                    "posX": round(field_rect.x0 / page.rect.width, 5),
                    "posY": round(field_rect.y0 / page.rect.height, 5),
                    "width": round(field_rect.width / page.rect.width, 5),
                    "height": round(field_rect.height / page.rect.height, 5),
                    "required": True,
                }
            if set(found) != {"employee", "representative"}:
                raise SignFieldsNotReady("Deben existir ambas zonas independientes.")
            return found
    except (ValueError, RuntimeError) as exc:
        if isinstance(exc, SignFieldsNotReady):
            raise
        raise SignFieldsNotReady("No se pudo interpretar el PDF de demostración.") from exc


def _validate_odoo(target, template_id: int) -> tuple[dict, list[int]]:
    fields = target.fields_get("sign.item")
    required = {
        "type_id": ("many2one", "sign.item.type"),
        "responsible_id": ("many2one", "sign.item.role"),
        "template_id": ("many2one", "sign.template"),
        "page": ("integer", None),
        "posX": ("float", None),
        "posY": ("float", None),
        "width": ("float", None),
        "height": ("float", None),
        "required": ("boolean", None),
    }
    for field, (kind, relation) in required.items():
        item = fields.get(field) or {}
        if item.get("type") != kind or (relation and item.get("relation") != relation):
            raise SignFieldsUnavailable("El esquema Odoo Sign de campos de firma no coincide.")
    rows = target.search_read("sign.template", [("id", "=", template_id)],
                              fields=["id", "sign_item_ids"], limit=2)
    if len(rows) != 1 or rows[0].get("id") != template_id:
        raise SignFieldsNotReady("No se encontró la plantilla de este expediente.")
    existing = rows[0].get("sign_item_ids") or []
    if not isinstance(existing, list):
        raise SignFieldsUnavailable("Odoo no devolvió los campos de la plantilla.")
    return fields, existing


def _roles_and_type(target) -> tuple[dict[str, int], int]:
    roles = target.search_read("sign.item.role", [], fields=["id", "name"], limit=100)
    mapped = {}
    for item in roles:
        role = sign_requests.canonical_role([item["id"], item.get("name")])
        if role:
            if role in mapped:
                raise SignFieldsUnavailable("Odoo contiene roles de firma ambiguos.")
            mapped[role] = item["id"]
    if set(mapped) != {"employee", "representative"}:
        raise SignFieldsUnavailable("Los roles de firma no están configurados en Odoo.")
    types = target.search_read("sign.item.type", [("id", "=", 1)],
                               fields=["id", "name"], limit=1)
    if (len(types) != 1 or types[0].get("id") != 1
            or str(types[0].get("name") or "").casefold() not in ("signature", "firma")):
        raise SignFieldsUnavailable("No se encontró el tipo de campo Firma esperado.")
    return mapped, 1


def _existing_matches(target, ids: list[int], expected: list[dict]) -> bool:
    if len(ids) != 2 or not all(type(i) is int and i > 0 for i in ids):
        return False
    rows = target.search_read(
        "sign.item", [("id", "in", ids)],
        fields=["id", "type_id", "responsible_id", "page", "posX", "posY",
                "width", "height", "required"], limit=3,
    )
    if len(rows) != 2 or {r.get("id") for r in rows} != set(ids):
        return False
    matched = set()
    for row in rows:
        role_id = sign_requests._m2o_id(row.get("responsible_id"))
        match = next((j for j, item in enumerate(expected)
                      if item["responsible_id"] == role_id), None)
        if match is None or match in matched:
            return False
        desired = expected[match]
        if (sign_requests._m2o_id(row.get("type_id")) != desired["type_id"]
                or row.get("page") != desired["page"]
                or row.get("required") is not True
                or any(abs(float(row.get(key) or 0) - desired[key]) > 0.001
                       for key in ("posX", "posY", "width", "height"))):
            return False
        matched.add(match)
    return len(matched) == 2


def _preflight(db: Session, employee_id: str, *, client=None, lock: bool = False):
    document = _document(db, employee_id, lock=lock)
    pdf = storage.read_employee_pdf_for_signing(
        employee_id=employee_id, key=document.storage_key,
        expected_bytes=document.size_bytes,
    )
    positions = _positions(pdf)
    target = client or staging.build_staging_client()
    _, current = _validate_odoo(target, document.odoo_sign_template_id)
    roles, type_id = _roles_and_type(target)
    expected = [
        {"type_id": type_id, "responsible_id": roles[role], **positions[role]}
        for role in ("employee", "representative")
    ]
    if current and not _existing_matches(target, current, expected):
        raise SignFieldsNotReady("La plantilla tiene campos distintos; no se modificarán.")
    return document, target, expected, bool(current)


def preview(db: Session, employee_id: str, *, client=None) -> dict:
    try:
        document, target, expected, done = _preflight(db, employee_id, client=client)
        return {
            "configured": done,
            "can_apply": not done,
            "staging_only": True,
            "roles": ["Empleado", "Representante legal"],
            "positions": [
                {k: value for k, value in item.items()
                 if k in ("page", "posX", "posY", "width", "height")}
                for item in expected
            ],
            "message": ("Ambas firmas ya están configuradas."
                        if done else "Dos zonas de firma detectadas sin superposición."),
        }
    except (staging.OdooNotConfigured, OdooClientError) as exc:
        raise SignFieldsUnavailable("No fue posible consultar los campos de Odoo staging.") from exc


def apply(db: Session, employee_id: str, *, client=None) -> dict:
    """Explicit HR action; one Odoo write, no sign.request, no emails."""
    try:
        document, target, expected, configured = _preflight(
            db, employee_id, client=client, lock=True,
        )
        if configured:
            db.commit()
            return preview(db, employee_id, client=target)
        # Odoo performs the two one2many creates in one remote transaction.
        target.write("sign.template", [document.odoo_sign_template_id], {
            "sign_item_ids": [[0, 0, item] for item in expected],
        })
        _, ids = _validate_odoo(target, document.odoo_sign_template_id)
        if not _existing_matches(target, ids, expected):
            raise SignFieldsUnavailable(
                "Odoo no confirmó los dos campos; no reintentes sin verificar."
            )
        db.commit()
        return preview(db, employee_id, client=target)
    except (staging.OdooNotConfigured, OdooClientError) as exc:
        db.rollback()
        raise SignFieldsUnavailable(
            "Resultado de configuración incierto. Revisa el estado antes de reintentar."
        ) from exc
    except Exception:
        db.rollback()
        raise
