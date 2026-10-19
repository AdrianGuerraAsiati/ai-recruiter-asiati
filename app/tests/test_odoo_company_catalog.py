"""Company catalog: only real active Odoo IDs can be selected for hiring."""
import pytest
from app.domains.odoo_sync import company_catalog, router as odoo_router


class FakeCompanyClient:
    def __init__(self):
        self.calls = []

    def fields_get(self, model, **kwargs):
        assert model == "res.company"
        return {"id": {}, "name": {}, "active": {}, "country_id": {}}

    def search_read(self, model, domain, *, fields, limit, order):
        assert model == "res.company"
        self.calls.append(domain)
        rows = [
            {"id": 21, "name": "Empresa Colombia", "country_id": [49, "Colombia"]},
            {"id": 22, "name": "Marca Asiati", "country_id": [49, "Colombia"]},
        ]
        ids = [x[2] for x in domain if x[0] == "id"]
        return [x for x in rows if x["id"] in ids] if ids else rows


def test_company_catalog_returns_authorized_odoo_companies():
    client = FakeCompanyClient()
    assert company_catalog.list_companies(client=client) == [
        {"id": 21, "name": "Empresa Colombia", "country": "Colombia"},
        {"id": 22, "name": "Marca Asiati", "country": "Colombia"},
    ]
    assert client.calls[0] == [("active", "=", True)]


def test_selected_company_is_checked_against_odoo_id():
    client = FakeCompanyClient()
    assert company_catalog.require_company(21, client=client)["name"] == "Empresa Colombia"
    with pytest.raises(company_catalog.OdooCompanyNotFound):
        company_catalog.require_company(999, client=client)
    with pytest.raises(company_catalog.OdooCompanyNotFound):
        company_catalog.require_company(0, client=client)
    assert client.calls[0] == [("id", "=", 21), ("active", "=", True)]
    assert client.calls[1] == [("id", "=", 999), ("active", "=", True)]


def test_companies_endpoint_uses_server_verified_catalog(monkeypatch):
    monkeypatch.setattr(odoo_router.company_catalog, "list_companies",
                        lambda: [{"id": 21, "name": "Empresa Colombia", "country": "Colombia"}])
    result = odoo_router.list_odoo_companies(_principal={})
    assert result["items"][0]["id"] == 21
