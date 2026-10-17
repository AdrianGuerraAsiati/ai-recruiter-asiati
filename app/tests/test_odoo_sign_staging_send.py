"""One-shot staging send and safe Odoo response reconciliation."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.domains.employee_documents import sign_send, sign_dispatch, sign_requests
from app.domains.employee_documents.models import EmployeeDocument
from app.integrations.odoo.client import OdooRpcError
from app.models import UserProfile


class FakeOdoo:
    def __init__(self, *, timeout=False, no_context=False, duplicate=False):
        self.timeout = timeout
        self.no_context = no_context
        self.duplicate = duplicate
        self.sent = False
        self.wizard = None
        self.create_count = 0
        self.send_count = 0

    def fields_get(self, model):
        models = {
            "sign.send.request": {
                "template_id": {"type": "many2one", "relation": "sign.template"},
                "signer_ids": {"type": "one2many", "relation": "sign.send.request.signer"},
                "set_sign_order": {"type": "boolean"},
                "subject": {"type": "char"},
            },
            "sign.send.request.signer": {
                "partner_id": {"type": "many2one", "relation": "res.partner"},
                "role_id": {"type": "many2one", "relation": "sign.item.role"},
                "mail_sent_order": {"type": "integer"},
            },
            "sign.template": {
                "sign_item_ids": {"type": "one2many", "relation": "sign.item"},
            },
            "sign.item": {
                "responsible_id": {"type": "many2one", "relation": "sign.item.role"},
            },
            "sign.item.role": {"name": {"type": "char"}},
            "res.partner": {"email": {"type": "char"}},
            "sign.request": {
                "id": {}, "subject": {"type": "char"},
                "template_id": {"type": "many2one", "relation": "sign.template"},
                "request_item_ids": {"type": "one2many", "relation": "sign.request.item"},
                "state": {"type": "selection"},
            },
            "sign.request.item": {
                "id": {}, "role_id": {"type": "many2one", "relation": "sign.item.role"},
                "state": {"type": "selection"}, "signer_email": {"type": "char"},
            },
        }
        return models[model]

    def search_read(self, model, domain, *, fields, limit):
        if model == "sign.template":
            return [{"id": 812, "sign_item_ids": [401, 402]}]
        if model == "sign.item":
            return [
                {"id": 401, "responsible_id": [51, "Empleado"]},
                {"id": 402, "responsible_id": [52, "Representante legal"]},
            ]
        if model == "sign.item.role":
            return [
                {"id": 51, "name": "Empleado"},
                {"id": 52, "name": "Representante legal"},
            ]
        if model == "res.partner":
            attribute, _, value = domain[0]
            addresses = {
                301: "empleado.adn360@example.invalid",
                302: "representante.adn360@example.invalid",
            }
            if attribute == "email":
                matches = [
                    {"id": partner_id, "email": address}
                    for partner_id, address in addresses.items()
                    if address == value
                ]
                return matches[:limit]
            assert attribute == "id"
            return [{"id": value, "email": addresses[value]}] if value in addresses else []
        if model == "sign.request.item":
            return [
                {"id": 501, "role_id": [51, "Empleado"],
                 "state": "sent", "signer_email": "empleado.adn360@example.invalid"},
                {"id": 502, "role_id": [52, "Representante legal"],
                 "state": "sent", "signer_email": "representante.adn360@example.invalid"},
            ]
        if model == "sign.request":
            if not self.sent:
                return []
            row = {
                "id": 139, "subject": self.wizard["subject"],
                "template_id": [812, "Contrato de prueba"],
                "request_item_ids": [501, 502], "state": "sent",
            }
            if self.duplicate and len(domain) == 2:
                return [row, dict(row, id=140)]
            return [row]
        raise AssertionError(f"Unexpected Odoo model {model}")

    def create(self, model, values):
        assert model == "sign.send.request"
        self.create_count += 1
        self.wizard = values
        assert values["set_sign_order"] is True
        assert [part[2]["mail_sent_order"] for part in values["signer_ids"]] == [1, 2]
        return 710

    def execute_kw(self, model, method, args=None, kwargs=None):
        assert (model, method, args) == (
            "sign.send.request", "send_request", [[710]],
        )
        self.send_count += 1
        self.sent = True
        if self.timeout:
            raise OdooRpcError("Transport timed out after committed send")
        if self.no_context:
            return {"type": "ir.actions.act_window_close"}
        return {"type": "ir.actions.client", "tag": "sign.Document",
                "context": {"id": 139, "token": "secret-must-never-be-exposed"}}


@pytest.fixture
def fixture(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    profile = UserProfile(
        cognito_sub="staging-send-fixture", email="profile@example.invalid",
        first_name="Prueba", last_name="Empleado", status="ACTIVE",
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    contract = EmployeeDocument(
        employee_id=profile.id, document_type="EMPLOYMENT_CONTRACT",
        review_status="APPROVED",
        storage_key=f"training/employee-documents/{profile.id}/unsigned.pdf",
        odoo_sign_source_key=f"training/employee-documents/{profile.id}/unsigned.pdf",
        odoo_sign_status="PREPARED", odoo_sign_template_id=812,
        original_filename="contrato.pdf", content_type="application/pdf", size_bytes=250,
    )
    db.add(contract)
    db.commit()
    db.refresh(contract)
    monkeypatch.setenv("ODOO_SIGN_TEST_EMPLOYEE_IDS", profile.id)
    monkeypatch.setenv("ODOO_SIGN_STAGING_TRACK_ENABLED", "true")
    monkeypatch.setenv(
        "ODOO_SIGN_TEST_SIGNER_EMAILS",
        "empleado.adn360@example.invalid,representante.adn360@example.invalid",
    )
    monkeypatch.setenv("ODOO_SIGN_STAGING_SEND_ENABLED", "true")
    yield db, profile, contract, monkeypatch
    db.close()
    engine.dispose()


def send(db, profile, target):
    return sign_send.send(
        db, profile.id, employee_partner_id=301,
        representative_partner_id=302, client=target,
    )


def test_send_once_links_verified_request_and_never_returns_token(fixture):
    db, profile, contract, monkeypatch = fixture
    odoo = FakeOdoo()
    response = send(db, profile, odoo)
    assert response["status"] == "SENT"
    assert response["request_id"] == 139
    assert response["emails_delivered"] is False
    assert "token" not in str(response)
    assert contract.odoo_sign_request_id == 139
    assert contract.odoo_sign_request_status == "PENDING_SIGNATURE"
    assert contract.odoo_sign_dispatch_status == "SENT"
    assert contract.odoo_sign_dispatch_subject == f"ADN360-STAGING-{contract.id}"
    assert odoo.create_count == odoo.send_count == 1
    with pytest.raises(sign_dispatch.DispatchNotReady, match="solicitud de firma vinculada"):
        send(db, profile, odoo)
    assert odoo.create_count == 1


def test_timeout_blocks_retries_and_reconciles_unique_remote_request(fixture):
    db, profile, contract, monkeypatch = fixture
    odoo = FakeOdoo(timeout=True)
    with pytest.raises(sign_send.DispatchOutcomeUnknown, match="No reintentar"):
        send(db, profile, odoo)
    assert contract.odoo_sign_dispatch_status == "UNKNOWN"
    assert contract.odoo_sign_request_id is None
    with pytest.raises(sign_dispatch.DispatchNotReady):
        send(db, profile, odoo)
    assert (odoo.create_count, odoo.send_count) == (1, 1)
    result = sign_send.reconcile(db, profile.id, client=odoo)
    assert result == {"status": "SENT", "request_id": 139, "staging_only": True}
    assert contract.odoo_sign_dispatch_status == "SENT"
    assert contract.odoo_sign_request_id == 139
    assert odoo.create_count == 1


def test_missing_action_context_can_recover_by_unique_subject(fixture):
    db, profile, contract, monkeypatch = fixture
    odoo = FakeOdoo(no_context=True)
    result = send(db, profile, odoo)
    assert result["request_id"] == 139
    assert contract.odoo_sign_dispatch_status == "SENT"


def test_ambiguous_remote_matches_remain_unknown_and_block_resend(fixture):
    db, profile, contract, monkeypatch = fixture
    odoo = FakeOdoo(timeout=True, duplicate=True)
    with pytest.raises(sign_send.DispatchOutcomeUnknown):
        send(db, profile, odoo)
    with pytest.raises(sign_send.DispatchOutcomeUnknown, match="Revisión manual"):
        sign_send.reconcile(db, profile.id, client=odoo)
    assert contract.odoo_sign_request_id is None
    assert contract.odoo_sign_dispatch_status == "UNKNOWN"
    assert odoo.send_count == 1


def test_no_remote_match_never_retries_staging_wizard(fixture):
    db, profile, contract, monkeypatch = fixture
    odoo = FakeOdoo(timeout=True)
    with pytest.raises(sign_send.DispatchOutcomeUnknown):
        send(db, profile, odoo)
    odoo.sent = False
    result = sign_send.reconcile(db, profile.id, client=odoo)
    assert result["status"] == "UNKNOWN"
    assert odoo.create_count == 1
    assert odoo.send_count == 1


def test_disabled_feature_never_writes_anything(fixture):
    db, profile, contract, monkeypatch = fixture
    monkeypatch.setenv("ODOO_SIGN_STAGING_SEND_ENABLED", "false")
    odoo = FakeOdoo()
    with pytest.raises(sign_dispatch.DispatchUnavailable, match="deshabilitado"):
        send(db, profile, odoo)
    assert odoo.create_count == odoo.send_count == 0
    assert contract.odoo_sign_dispatch_status == "NOT_SENT"


def test_existing_remote_subject_prevents_send(fixture):
    db, profile, contract, monkeypatch = fixture
    odoo = FakeOdoo()
    odoo.sent = True
    odoo.wizard = {"subject": f"ADN360-STAGING-{contract.id}"}
    with pytest.raises(sign_send.DispatchConflict, match="Ya existe"):
        send(db, profile, odoo)
    assert contract.odoo_sign_dispatch_status == "NOT_SENT"
    assert odoo.create_count == odoo.send_count == 0


def test_reconcile_cannot_run_before_first_send(fixture):
    db, profile, contract, monkeypatch = fixture
    with pytest.raises(sign_send.DispatchConflict, match="No existe"):
        sign_send.reconcile(db, profile.id, client=FakeOdoo())
    assert contract.odoo_sign_dispatch_status == "NOT_SENT"


def test_automatic_preflight_resolves_signers_without_exposing_odoo_ids(fixture):
    db, profile, contract, _ = fixture
    odoo = FakeOdoo()
    result = sign_dispatch.preview_automatic(db, profile.id, client=odoo)
    assert result["validated"] is True
    assert result["request_created"] is False
    assert result["emails_sent"] is False
    assert "partner_id" not in result
    assert odoo.create_count == odoo.send_count == 0
    assert contract.odoo_sign_request_id is None


def test_automatic_send_stores_generated_request_without_contact_ids_from_hr(fixture):
    db, profile, contract, _ = fixture
    odoo = FakeOdoo()
    result = sign_send.send_automatic(db, profile.id, client=odoo)
    assert result["status"] == "SENT"
    assert contract.odoo_sign_request_id == 139
    assert odoo.create_count == odoo.send_count == 1


@pytest.mark.parametrize("addresses", [
    "empleado.adn360@example.invalid,empleado.adn360@example.invalid",
    "representante.adn360@example.invalid,empleado.adn360@example.invalid",
    "somebody@example.com,representante.adn360@example.invalid",
    "empleado.adn360@example.invalid",
    "",
])
def test_automatic_send_rejects_invalid_fixtures_without_odoo_writes(
    fixture, addresses,
):
    db, profile, contract, monkeypatch = fixture
    monkeypatch.setenv("ODOO_SIGN_TEST_SIGNER_EMAILS", addresses)
    odoo = FakeOdoo()
    with pytest.raises(
        (sign_dispatch.DispatchUnavailable, sign_dispatch.DispatchNotReady,
         sign_requests.SignTrackingUnavailable)
    ):
        sign_send.send_automatic(db, profile.id, client=odoo)
    assert odoo.create_count == odoo.send_count == 0
    assert contract.odoo_sign_request_id is None


def test_automatic_send_disabled_before_any_remote_reads(fixture, monkeypatch):
    db, profile, contract, _ = fixture
    monkeypatch.setenv("ODOO_SIGN_STAGING_SEND_ENABLED", "false")
    odoo = FakeOdoo()
    with pytest.raises(sign_dispatch.DispatchUnavailable, match="deshabilitado"):
        sign_send.send_automatic(db, profile.id, client=odoo)
    assert odoo.create_count == odoo.send_count == 0
    assert contract.odoo_sign_request_id is None


def test_automatic_lookup_rejects_duplicate_contacts(fixture):
    db, profile, _, monkeypatch = fixture
    odoo = FakeOdoo()
    previous = odoo.search_read
    def duplicated(model, domain, *, fields, limit):
        if model == "res.partner" and domain[0][0] == "email":
            item = previous(model, domain, fields=fields, limit=limit)[0]
            return [item, dict(item, id=950)]
        return previous(model, domain, fields=fields, limit=limit)
    odoo.search_read = duplicated
    with pytest.raises(sign_dispatch.DispatchNotReady, match="único"):
        sign_dispatch.preview_automatic(db, profile.id, client=odoo)
    assert odoo.create_count == odoo.send_count == 0
