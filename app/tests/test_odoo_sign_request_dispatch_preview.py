"""Read-only Odoo 18 Sign wizard preflight for exactly two fictitious signers."""
from types import SimpleNamespace

import pytest

from app.domains.employee_documents import sign_dispatch, signing, sign_requests


class FakeOdoo:
    def __init__(self):
        self.models = {
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
            "res.partner": {"email": {"type": "char"}},
            "sign.item.role": {"name": {"type": "char"}},
        }
        self.role_names = ["Empleado", "Representante legal"]
        self.sign_item_roles = [51, 52]
        self.partner_emails = {
            301: "empleado@example.invalid",
            302: "representante@example.invalid",
        }
        self.items = [401, 402]
        self.calls = []

    def fields_get(self, model):
        self.calls.append(("fields_get", model))
        return self.models[model]

    def search_read(self, model, domain, *, fields, limit):
        self.calls.append(("search_read", model))
        if model == "sign.template":
            return [{"id": 128, "sign_item_ids": self.items}]
        if model == "sign.item":
            return [
                {"id": 401 + i, "responsible_id": [self.sign_item_roles[i], self.role_names[i]]}
                for i in range(len(self.items))
            ]
        if model == "sign.item.role":
            return [
                {"id": 51 + i, "name": name}
                for i, name in enumerate(self.role_names)
            ]
        if model == "res.partner":
            partner_id = domain[0][2]
            if partner_id not in self.partner_emails:
                return []
            return [{"id": partner_id, "email": self.partner_emails[partner_id]}]
        raise AssertionError("Unexpected Odoo model")

    def create(self, *args, **kwargs):
        pytest.fail("Preflight must never write to Odoo")

    def execute_kw(self, *args, **kwargs):
        pytest.fail("Preflight must never call send_request")


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setenv("ODOO_SIGN_TEST_EMPLOYEE_IDS", "employee-test")
    monkeypatch.setenv("ODOO_SIGN_STAGING_TRACK_ENABLED", "true")
    monkeypatch.setenv(
        "ODOO_SIGN_TEST_SIGNER_EMAILS",
        "empleado@example.invalid,representante@example.invalid",
    )
    contract = SimpleNamespace(
        odoo_sign_status="PREPARED",
        odoo_sign_template_id=128,
        review_status="APPROVED",
        storage_key="training/employee-documents/employee-test/original.pdf",
        odoo_sign_source_key="training/employee-documents/employee-test/original.pdf",
        odoo_sign_request_id=None,
    )
    monkeypatch.setattr(signing, "_contract", lambda db, employee_id: contract)
    target = FakeOdoo()
    return target, contract


def preflight(target):
    return sign_dispatch.preview(
        object(), "employee-test", employee_partner_id=301,
        representative_partner_id=302, client=target,
    )


def test_two_signers_exact_template_order_and_no_remote_writes(setup):
    target, contract = setup
    result = preflight(target)
    assert result == {
        "validated": True, "environment": "staging", "template_id": 128,
        "employee_partner_id": 301, "representative_partner_id": 302,
        "signing_order": ["Empleado", "Representante legal"],
        "send_enabled": False, "emails_sent": False, "request_created": False,
        "note": "Configuración validada; pendiente confirmar el comportamiento de send_request() antes de habilitar el envío.",
    }
    assert all(call[0] in ("fields_get", "search_read") for call in target.calls)
    assert contract.odoo_sign_request_id is None


@pytest.mark.parametrize("target_change, expected_exception", [
    (lambda x: x.models["sign.send.request"].pop("subject"), sign_dispatch.DispatchUnavailable),
    (lambda x: x.models["sign.send.request.signer"]["role_id"].update(relation="res.partner"),
     sign_dispatch.DispatchUnavailable),
    (lambda x: x.models["sign.item"].clear(), sign_dispatch.DispatchUnavailable),
    (lambda x: setattr(x, "role_names", ["Cliente", "Representante legal"]),
     sign_dispatch.DispatchNotReady),
    (lambda x: setattr(x, "sign_item_roles", [51, 51]),
     sign_dispatch.DispatchNotReady),
    (lambda x: setattr(x, "items", []), sign_dispatch.DispatchNotReady),
    (lambda x: x.partner_emails.update({301: "someone@asiati.com.co"}),
     sign_dispatch.DispatchNotReady),
    (lambda x: x.partner_emails.pop(302), sign_dispatch.DispatchNotReady),
])
def test_preflight_fail_closed_on_invalid_wizard_template_or_contacts(
    setup, target_change, expected_exception,
):
    target, contract = setup
    target_change(target)
    with pytest.raises(expected_exception):
        preflight(target)
    assert contract.odoo_sign_request_id is None


@pytest.mark.parametrize("field, value", [
    ("odoo_sign_status", "NOT_PREPARED"),
    ("odoo_sign_template_id", None),
    ("review_status", "PENDING_REVIEW"),
    ("odoo_sign_source_key", "different.pdf"),
    ("odoo_sign_request_id", 139),
])
def test_preflight_rejects_unapproved_wrong_version_or_already_sent(
    setup, field, value,
):
    target, contract = setup
    setattr(contract, field, value)
    with pytest.raises(sign_dispatch.DispatchNotReady):
        preflight(target)
    assert target.calls == []


@pytest.mark.parametrize("employee_partner_id, representative_partner_id", [
    (301, 301), (0, 302), (301, -1), ("301", 302), (True, 302),
])
def test_preflight_rejects_invalid_partner_ids_before_connecting(
    setup, employee_partner_id, representative_partner_id,
):
    target, _ = setup
    with pytest.raises(sign_dispatch.DispatchNotReady):
        sign_dispatch.preview(
            object(), "employee-test",
            employee_partner_id=employee_partner_id,
            representative_partner_id=representative_partner_id,
            client=target,
        )
    assert target.calls == []


def test_preflight_rejects_unallowlisted_employee_before_odoo(setup):
    target, _ = setup
    with pytest.raises(sign_requests.SignTrackingUnavailable):
        sign_dispatch.preview(
            object(), "real-employee",
            employee_partner_id=301, representative_partner_id=302,
            client=target,
        )
    assert target.calls == []


def test_schema_with_role_id_instead_of_responsible_id(setup):
    target, _ = setup
    target.models["sign.item"] = {
        "role_id": {"type": "many2one", "relation": "sign.item.role"}
    }
    original = target.search_read
    def swapped(model, domain, *, fields, limit):
        if model == "sign.item":
            return [
                {"id": 401 + i, "role_id": [51 + i, target.role_names[i]]}
                for i in range(2)
            ]
        return original(model, domain, fields=fields, limit=limit)
    target.search_read = swapped
    assert preflight(target)["validated"] is True


def test_sending_flag_does_not_trigger_mutations(setup, monkeypatch):
    target, _ = setup
    monkeypatch.setenv("ODOO_SIGN_STAGING_SEND_ENABLED", "true")
    # A flag alone does not authorize writes in the preflight-only code path.
    assert sign_dispatch.sending_enabled() is True
    assert preflight(target)["request_created"] is False


def test_odoo_wizard_payload_has_exact_two_roles_and_deterministic_order():
    wizard = sign_dispatch.build_wizard_values(
        template_id=128, employee_partner_id=301, representative_partner_id=302,
        employee_role_id=51, representative_role_id=52,
    )
    assert wizard == {
        "template_id": 128,
        "subject": "ADN360 - Firma de contrato laboral (PRUEBA)",
        "set_sign_order": True,
        "signer_ids": [
            [0, 0, {"partner_id": 301, "role_id": 51, "mail_sent_order": 1}],
            [0, 0, {"partner_id": 302, "role_id": 52, "mail_sent_order": 2}],
        ],
    }


def test_odoo_wizard_payload_rejects_same_partner_role_or_invalid_identifier():
    for values in (
        dict(template_id=0, employee_partner_id=301, representative_partner_id=302,
             employee_role_id=51, representative_role_id=52),
        dict(template_id=128, employee_partner_id=301, representative_partner_id=301,
             employee_role_id=51, representative_role_id=52),
        dict(template_id=128, employee_partner_id=301, representative_partner_id=302,
             employee_role_id=51, representative_role_id=51),
        dict(template_id=128, employee_partner_id=True, representative_partner_id=302,
             employee_role_id=51, representative_role_id=52),
    ):
        with pytest.raises(sign_dispatch.DispatchNotReady):
            sign_dispatch.build_wizard_values(**values)


def test_staging_credentials_missing_fails_sanitized(setup, monkeypatch):
    target, contract = setup
    def disconnected():
        from app.domains.odoo_sync import staging
        raise staging.OdooNotConfigured("Secret not present")
    monkeypatch.setattr(sign_dispatch.staging, "build_staging_client", disconnected)
    with pytest.raises(sign_dispatch.DispatchUnavailable, match="no configurada"):
        sign_dispatch.preview(
            object(), "employee-test", employee_partner_id=301,
            representative_partner_id=302,
        )
    assert contract.odoo_sign_request_id is None


def test_remote_unavailable_fails_without_leaking_details(setup):
    from app.integrations.odoo.client import OdooRpcError
    target, contract = setup
    def no_rpc(model):
        raise OdooRpcError("Sensitive connection detail")
    target.fields_get = no_rpc
    with pytest.raises(sign_dispatch.DispatchUnavailable, match="No fue posible consultar"):
        preflight(target)
    assert contract.odoo_sign_request_id is None


def test_odoo_english_employee_role_works_in_staging_wizard_preflight(setup):
    target, _ = setup
    target.role_names = ["Employee", "Representante legal"]
    result = preflight(target)
    assert result["validated"] is True


def test_english_and_spanish_employee_role_cannot_both_replace_legal_role(setup):
    target, _ = setup
    target.role_names = ["Employee", "Empleado"]
    with pytest.raises(sign_dispatch.DispatchNotReady, match="Empleado y Representante legal"):
        preflight(target)
