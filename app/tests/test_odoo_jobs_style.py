"""Tests for the idempotent ASIATI Odoo careers-page visual customization."""

from app.scripts import style_odoo_jobs_page


class FakeOdooClient:
    def __init__(self, *, existing_custom=None):
        self.existing_custom = existing_custom
        self.created = []
        self.written = []

    def search_read(self, model, domain, *, fields=None, limit=None):
        assert model == "ir.ui.view"
        key = domain[0][2]
        if key == style_odoo_jobs_page.BASE_VIEW_KEY:
            return [{
                "id": 120,
                "name": "Jobs",
                "key": style_odoo_jobs_page.BASE_VIEW_KEY,
                "type": "qweb",
                "active": True,
            }]
        if key == style_odoo_jobs_page.VIEW_KEY:
            return [dict(self.existing_custom)] if self.existing_custom else []
        raise AssertionError(domain)

    def create(self, model, values):
        assert model == "ir.ui.view"
        self.created.append(dict(values))
        return 901

    def write(self, model, ids, values):
        assert model == "ir.ui.view"
        self.written.append((list(ids), dict(values)))
        return True


def test_jobs_style_creates_inherited_qweb_view():
    client = FakeOdooClient()

    result = style_odoo_jobs_page.apply_jobs_style(client)

    assert result["action"] == "CREATED"
    assert result["view_id"] == 901
    assert len(client.created) == 1
    values = client.created[0]
    assert values["inherit_id"] == 120
    assert values["type"] == "qweb"
    assert values["mode"] == "extension"
    assert values["key"] == style_odoo_jobs_page.VIEW_KEY
    assert ".o_website_hr_recruitment_jobs_list" in values["arch_db"]
    assert "-webkit-line-clamp: 3" in values["arch_db"]
    assert "#jobs_grid_right" in values["arch_db"]


def test_jobs_style_updates_existing_view_instead_of_duplicating():
    client = FakeOdooClient(existing_custom={
        "id": 902,
        "name": "Old style",
        "key": style_odoo_jobs_page.VIEW_KEY,
        "active": True,
        "inherit_id": [120, "Jobs"],
    })

    result = style_odoo_jobs_page.apply_jobs_style(client)

    assert result["action"] == "UPDATED"
    assert result["view_id"] == 902
    assert client.created == []
    assert client.written[0][0] == [902]
    assert client.written[0][1]["inherit_id"] == 120
