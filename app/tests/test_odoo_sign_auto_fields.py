"""Signature regions are derived from synthetic PDF drawings, never copied blindly."""
from types import SimpleNamespace

import fitz
import pytest

from app.domains.employee_documents import sign_fields, signing


def demo_pdf(*, duplicate_role=False, box_count=2, marker=True) -> bytes:
    pdf = fitz.open()
    page = pdf.new_page(width=595.2756, height=841.89)
    if marker:
        page.insert_text((48, 220), "SOLO PRUEBA - SIN VALIDEZ CONTRACTUAL")
    labels = ["Empleado", "Empleado" if duplicate_role else "Representante legal"]
    boxes = [
        fitz.Rect(47, 595, 289, 707),
        fitz.Rect(305, 595, 547, 707),
    ]
    for label, rect in zip(labels, boxes[:box_count]):
        page.draw_rect(rect, color=(.5, .6, .7), dashes="[ 4 4 ] 0")
        page.insert_text((rect.x0 + 12, rect.y0 + 22), label)
        page.insert_text((rect.x0 + 12, rect.y0 + 36), "Zona reservada para la firma")
        page.insert_text((rect.x0 + 12, rect.y0 + 99), "Firmante")
    payload = pdf.tobytes()
    pdf.close()
    return payload


class FakeOdoo:
    def __init__(self):
        self.items = []
        self.writes = []
        self.roles = ["Employee", "Representante legal"]
        self.reference_roles = ["Employee", "Representante legal"]
        self.reference_missing = False
        self.good_schema = True

    def fields_get(self, model):
        assert model == "sign.item"
        fields = {
            "type_id": {"type": "many2one", "relation": "sign.item.type"},
            "responsible_id": {"type": "many2one", "relation": "sign.item.role"},
            "template_id": {"type": "many2one", "relation": "sign.template"},
            "page": {"type": "integer"},
            "posX": {"type": "float"},
            "posY": {"type": "float"},
            "width": {"type": "float"},
            "height": {"type": "float"},
            "required": {"type": "boolean"},
        }
        if not self.good_schema:
            fields.pop("template_id")
        return fields

    def search_read(self, model, domain, *, fields, limit):
        if model == "sign.template":
            queried = domain[0][2]
            if queried == 128:
                return [] if self.reference_missing else [
                    {"id": 128, "sign_item_ids": [762, 763]}
                ]
            assert queried == 129
            return [{"id": 129, "sign_item_ids": [item["id"] for item in self.items]}]
        if model == "sign.item.role":
            # Duplicate global role names are valid in Odoo; production code
            # must never rely on scanning and uniquely matching all of them.
            return [{"id": 3 + i * 2, "name": label}
                    for i, label in enumerate(self.roles)]
        if model == "sign.item.type":
            return [{"id": 1, "name": "Signature"}]
        if model == "sign.item":
            if domain == [("id", "in", [762, 763])]:
                return [
                    {"id": 762 + i, "type_id": [1, "Signature"],
                     "responsible_id": [3 + i * 2, label], "required": True}
                    for i, label in enumerate(self.reference_roles)
                ]
            return [{**item,
                     "type_id": [item["type_id"], "Signature"],
                     "responsible_id": [item["responsible_id"], "Role"]}
                    for item in self.items]
        raise AssertionError(model)

    def write(self, model, ids, values):
        assert model == "sign.template" and ids == [129]
        assert len(values["sign_item_ids"]) == 2
        self.writes.append(values)
        for i, command in enumerate(values["sign_item_ids"]):
            assert command[:2] == [0, 0]
            self.items.append({"id": 761 + i, **command[2]})
        return True


@pytest.fixture
def setup(monkeypatch):
    profile = "test-profile-129"
    monkeypatch.setenv("ODOO_SIGN_PRODUCTION_ENABLED", "true")
    monkeypatch.setenv("ODOO_SIGN_TEST_EMPLOYEE_IDS", profile)
    document = SimpleNamespace(
        odoo_sign_status="PREPARED", odoo_sign_environment="production",
        odoo_sign_request_id=None,
        odoo_sign_dispatch_status="NOT_SENT",
        review_status="APPROVED", odoo_sign_template_id=129,
        original_filename="ADN360_contrato_ficticio_prueba_Odoo_Sign.pdf",
        storage_key=f"training/employee-documents/{profile}/demo.pdf",
        odoo_sign_source_key=f"training/employee-documents/{profile}/demo.pdf",
        size_bytes=700,
    )
    monkeypatch.setattr(signing, "_contract", lambda db, employee_id, lock=False: document)
    monkeypatch.setattr(sign_fields.storage, "read_employee_pdf_for_signing",
                        lambda **kwargs: demo_pdf())
    db = SimpleNamespace(commit=lambda: None, rollback=lambda: None)
    return db, profile, document, FakeOdoo(), monkeypatch


def test_demo_pdf_detects_separate_boxes_without_covering_text():
    positions = sign_fields._positions(demo_pdf())
    assert set(positions) == {"employee", "representative"}
    employee = positions["employee"]
    representative = positions["representative"]
    assert employee["page"] == representative["page"] == 1
    assert employee["posX"] < representative["posX"]
    assert employee["posY"] == representative["posY"]
    assert employee["posX"] + employee["width"] < representative["posX"]
    assert 0 < employee["width"] < 1 and 0 < employee["height"] < 0.1
    assert employee["required"] and representative["required"]


def test_one_time_auto_placement_is_idempotent_and_never_sends_mail(setup):
    db, profile, document, target, _ = setup
    before = sign_fields.preview(db, profile, client=target)
    assert before["can_apply"] is True
    assert not before["configured"]
    result = sign_fields.apply(db, profile, client=target)
    assert result["configured"] is True
    assert len(target.writes) == 1
    assert len(target.items) == 2
    assert sorted(item["responsible_id"] for item in target.items) == [3, 5]
    assert all(item["required"] for item in target.items)
    assert sign_fields.apply(db, profile, client=target)["configured"] is True
    assert len(target.writes) == 1
    assert document.odoo_sign_request_id is None


@pytest.mark.parametrize("kwargs", [
    {"box_count": 1}, {"duplicate_role": True},
])
def test_missing_or_ambiguous_demo_regions_never_write(setup, kwargs):
    db, profile, document, target, monkeypatch = setup
    monkeypatch.setattr(sign_fields.storage, "read_employee_pdf_for_signing",
                        lambda **unused: demo_pdf(**kwargs))
    with pytest.raises(sign_fields.SignFieldsNotReady):
        sign_fields.apply(db, profile, client=target)
    assert target.writes == []


def test_existing_other_template_fields_are_not_overwritten(setup):
    db, profile, document, target, _ = setup
    target.items = [{"id": 800, "type_id": 1, "responsible_id": 3, "page": 1,
                     "posX": .1, "posY": .6, "width": .4, "height": .04, "required": True}]
    with pytest.raises(sign_fields.SignFieldsNotReady, match="distintos"):
        sign_fields.apply(db, profile, client=target)
    assert target.writes == []


def test_changed_odoo_sign_item_schema_fails_closed(setup):
    db, profile, document, target, _ = setup
    target.good_schema = False
    with pytest.raises(sign_fields.SignFieldsUnavailable, match="esquema"):
        sign_fields.preview(db, profile, client=target)
    assert target.writes == []


def test_reject_staging_document_but_accept_valid_real_pdf_name(setup):
    db, profile, document, target, _ = setup
    document.odoo_sign_environment = "staging"
    with pytest.raises(sign_fields.SignFieldsNotReady, match="Odoo Test"):
        sign_fields.apply(db, profile, client=target)
    document.odoo_sign_environment = "production"
    document.original_filename = "contrato_real.pdf"
    result = sign_fields.preview(db, profile, client=target)
    assert result["can_apply"] is True
    assert target.writes == []


def test_cannot_position_signatures_after_request_sent(setup):
    db, profile, document, target, _ = setup
    document.odoo_sign_request_id = 139
    with pytest.raises(sign_fields.SignFieldsNotReady, match="sin solicitud"):
        sign_fields.apply(db, profile, client=target)
    assert target.writes == []


def test_duplicate_global_role_names_do_not_block_verified_reference(setup):
    db, profile, document, target, _ = setup
    target.roles = [
        "Employee", "Empleado", "Representante legal", "Legal representative",
    ]
    with pytest.raises(sign_fields.SignFieldsUnavailable, match="duplicados"):
        sign_fields.preview(db, profile, client=target)
    assert target.writes == []


def test_missing_reference_template_fails_closed_without_writing(setup):
    db, profile, document, target, _ = setup
    target.roles = ["Representante legal"]
    with pytest.raises(sign_fields.SignFieldsUnavailable, match="roles"):
        sign_fields.preview(db, profile, client=target)
    assert target.writes == []


def test_duplicate_reference_roles_do_not_write(setup):
    db, profile, document, target, _ = setup
    target.roles = ["Employee", "Empleado", "Representante legal"]
    with pytest.raises(sign_fields.SignFieldsUnavailable, match="duplicados"):
        sign_fields.apply(db, profile, client=target)
    assert target.writes == []


def test_unrecognized_reference_role_is_rejected(setup):
    db, profile, document, target, _ = setup
    target.roles = ["Customer", "Representante legal"]
    with pytest.raises(sign_fields.SignFieldsUnavailable, match="roles"):
        sign_fields.apply(db, profile, client=target)
    assert target.writes == []


def test_extra_text_inside_signature_zone_is_rejected():
    pdf = fitz.open(stream=demo_pdf(), filetype="pdf")
    page = pdf[0]
    page.insert_text((70, 659), "NO TAPAR ESTE TEXTO")
    modified = pdf.tobytes()
    pdf.close()
    with pytest.raises(sign_fields.SignFieldsNotReady, match="superpone"):
        sign_fields._positions(modified)
