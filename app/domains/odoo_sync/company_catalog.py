"""Read-only Odoo company catalog for explicit hiring company selection.

Company IDs are validated against the same Odoo connection used by employee sync.
Names supplied by the browser are never trusted for a selected company.
"""

from __future__ import annotations

from app.domains.odoo_sync import integration


class OdooCompanyNotFound(ValueError):
    """No active accessible company corresponds to the supplied ID."""


def _rows(client, domain, *, limit: int) -> list[dict]:
    available = client.fields_get("res.company", attributes=("type",))
    requested = ["id", "name"]
    if "active" in available:
        domain = [*domain, ("active", "=", True)]
    if "country_id" in available:
        requested.append("country_id")
    return client.search_read("res.company", domain, fields=requested, limit=limit, order="name asc")


def _public_company(row: dict) -> dict:
    country = row.get("country_id")
    return {
        "id": int(row["id"]),
        "name": str(row.get("name") or "").strip(),
        "country": str(country[1]) if isinstance(country, (list, tuple)) and len(country) > 1 else None,
    }


def list_companies(*, client=None) -> list[dict]:
    target = client or integration.build_odoo_client()
    rows = _rows(target, [], limit=250)
    return [item for item in (_public_company(row) for row in rows) if item["name"]]


def require_company(company_id: int, *, client=None) -> dict:
    if type(company_id) is not int or company_id <= 0:
        raise OdooCompanyNotFound("Selecciona una empresa válida de Odoo.")
    target = client or integration.build_odoo_client()
    rows = _rows(target, [("id", "=", company_id)], limit=2)
    if len(rows) != 1 or int(rows[0].get("id") or 0) != company_id:
        raise OdooCompanyNotFound("La empresa seleccionada ya no está disponible en Odoo.")
    company = _public_company(rows[0])
    if not company["name"]:
        raise OdooCompanyNotFound("La empresa seleccionada no tiene nombre.")
    return company
