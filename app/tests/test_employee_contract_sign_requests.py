"""Read-only link and state tracking for fictitious Sign request E2E."""
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.domains.employee_documents import sign_requests
from app.domains.employee_documents.models import EmployeeDocument
from app.models import UserProfile


class FakeSign:
    def __init__(self, *, template=812, roles=None, emails=None, states=None,
                 overall="sent", malformed=False):
        self.template = template
        self.roles = roles or ["Empleado", "Representante legal"]
        self.emails = emails or ["empleado@example.invalid", "representante@example.invalid"]
        self.states = states or ["sent", "sent"]
        self.overall = overall
        self.malformed = malformed
        self.calls = []

    def fields_get(self, model):
        self.calls.append(("fields_get", model))
        if model == "sign.request":
            fields = ("id", "template_id", "request_item_ids", "state")
        elif model == "sign.request.item":
            fields = ("id", "role_id", "state", "signer_email")
            if self.malformed:
                fields = ("id", "role_id", "state")
        else:
            raise AssertionError("unexpected model")
        return {field: {} for field in fields}

    def search_read(self, model, domain, *, fields, limit):
        self.calls.append(("search_read", model))
        if model == "sign.request":
            return [{"id": 139, "template_id": [self.template, "Plantilla de prueba"],
                     "request_item_ids": [301, 302], "state": self.overall}]
        if model == "sign.request.item":
            return [
                {"id": 301 + i, "role_id": [10 + i, role],
                 "signer_email": self.emails[i], "state": self.states[i]}
                for i, role in enumerate(self.roles)
            ]
        raise AssertionError("unexpected model")


@pytest.fixture
def fixture(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    employee = UserProfile(cognito_sub="test-sign", email="test@example.invalid",
                           first_name="Empleado", last_name="Prueba", status="ACTIVE")
    db.add(employee)
    db.commit()
    db.refresh(employee)
    contract = EmployeeDocument(
        employee_id=employee.id,
        document_type="EMPLOYMENT_CONTRACT",
        original_filename="contrato.pdf",
        content_type="application/pdf",
        size_bytes=100,
        storage_key=f"training/employee-documents/{employee.id}/contrato.pdf",
        review_status="APPROVED",
        odoo_sign_status="PREPARED",
        odoo_sign_template_id=812,
        odoo_sign_source_key=f"training/employee-documents/{employee.id}/contrato.pdf",
    )
    db.add(contract)
    db.commit()
    db.refresh(contract)
    monkeypatch.setenv("ODOO_SIGN_STAGING_TRACK_ENABLED", "true")
    monkeypatch.setenv("ODOO_SIGN_TEST_EMPLOYEE_IDS", employee.id)
    monkeypatch.setenv("ODOO_SIGN_TEST_SIGNER_EMAILS",
                       "empleado@example.invalid,representante@example.invalid")
    yield db, employee, contract
    db.close()
    engine.dispose()


def test_link_and_refresh_states_without_odoo_writes(fixture):
    db, employee, contract = fixture
    fake = FakeSign()
    result = sign_requests.track(db, employee.id, request_id=139, client=fake)
    assert result["request_id"] == 139
    assert result["status"] == "PENDING_SIGNATURE"
    assert result["signed_pdf_archived"] is False
    assert contract.odoo_sign_request_id == 139
    assert set(method for method, _ in fake.calls) == {"fields_get", "search_read"}

    partial = FakeSign(states=["signed", "sent"])
    result = sign_requests.track(db, employee.id, client=partial)
    assert result["status"] == "PARTIALLY_SIGNED"
    assert result["employee"] == "signed"
    assert result["representative"] == "sent"

    completed = FakeSign(states=["signed", "signed"], overall="signed")
    result = sign_requests.track(db, employee.id, client=completed)
    assert result["status"] == "SIGNED"
    assert contract.odoo_sign_completed_at is not None
    assert sign_requests.track(db, employee.id, client=completed)["status"] == "SIGNED"


def test_remote_request_signed_alone_does_not_complete_contract(fixture):
    db, employee, _ = fixture
    data = sign_requests.track(db, employee.id, request_id=139,
                               client=FakeSign(overall="signed", states=["sent", "signed"]))
    assert data["status"] == "PARTIALLY_SIGNED"


@pytest.mark.parametrize("fake", [
    FakeSign(template=999),
    FakeSign(roles=["Cliente", "Representante legal"]),
    FakeSign(emails=["real@asiati.com.co", "representante@example.invalid"]),
    FakeSign(emails=["empleado@example.invalid", "empleado@example.invalid"]),
])
def test_link_denies_wrong_template_roles_or_nonallowlisted_signer(fixture, fake):
    db, employee, contract = fixture
    with pytest.raises(sign_requests.SignTrackingConflict):
        sign_requests.track(db, employee.id, request_id=139, client=fake)
    assert contract.odoo_sign_request_id is None


def test_link_denies_unknown_schema_and_wrong_id(fixture):
    db, employee, contract = fixture
    with pytest.raises(sign_requests.SignTrackingUnavailable, match="estructura"):
        sign_requests.track(db, employee.id, request_id=139,
                            client=FakeSign(malformed=True))
    with pytest.raises(sign_requests.SignTrackingConflict, match="No existe"):
        sign_requests.track(db, employee.id, request_id=140,
                            client=FakeSign())
    assert contract.odoo_sign_request_id is None


def test_staging_disabled_does_not_call_odoo(fixture, monkeypatch):
    db, employee, contract = fixture
    monkeypatch.delenv("ODOO_SIGN_STAGING_TRACK_ENABLED")
    fake = FakeSign()
    with pytest.raises(sign_requests.SignTrackingUnavailable, match="deshabilitado"):
        sign_requests.track(db, employee.id, request_id=139, client=fake)
    assert fake.calls == []
    assert contract.odoo_sign_request_id is None


def test_idempotence_rejects_reattaching_different_request(fixture):
    db, employee, contract = fixture
    sign_requests.track(db, employee.id, request_id=139, client=FakeSign())
    with pytest.raises(sign_requests.SignTrackingConflict, match="otra solicitud"):
        sign_requests.track(db, employee.id, request_id=140, client=FakeSign())
    assert contract.odoo_sign_request_id == 139


def test_canceled_and_expired_are_not_signed(fixture):
    db, employee, _ = fixture
    assert sign_requests.track(
        db, employee.id, request_id=139,
        client=FakeSign(overall="cancelled", states=["signed", "sent"]),
    )["status"] == "CANCELLED"
    assert sign_requests.track(
        db, employee.id, client=FakeSign(overall="expired", states=["signed", "signed"]),
    )["status"] == "EXPIRED"
