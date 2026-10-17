"""Guarded Odoo Sign signed-contract archive: no Odoo writes or mail."""
import base64
import hashlib

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.domains.employee_documents import signed_artifacts, sign_requests
from app.domains.employee_documents.models import EmployeeDocument
from app.models import UserProfile

PDF = b"%PDF-1.7\n" + b"x" * 228 + b"\n%%EOF\n"


class FakeCompletedSign:
    def __init__(self, *, mimetype="application/pdf", changed_field=False, signed=True):
        self.mimetype = mimetype
        self.changed_field = changed_field
        self.signed = signed
        self.calls = []

    def fields_get(self, model):
        self.calls.append(("fields_get", model))
        if model == "sign.request":
            return {"completed_document_attachment_id": (
                {"type": "binary", "relation": None}
                if self.changed_field else
                {"type": "many2one", "relation": "ir.attachment"}
            )}
        if model == "ir.attachment":
            return {field: {} for field in ("id", "datas", "mimetype", "name", "file_size")}
        raise AssertionError("Unexpected model")

    def search_read(self, model, domain, *, fields, limit):
        self.calls.append(("search_read", model))
        if model == "sign.request":
            return [{"id": 139, "completed_document_attachment_id": [990, "Firmado"]}]
        if model == "ir.attachment":
            return [{"id": 990, "mimetype": self.mimetype,
                     "name": "Contrato firmado.pdf", "file_size": len(PDF),
                     "datas": base64.b64encode(PDF).decode("ascii")}]
        raise AssertionError("Unexpected model")


@pytest.fixture
def fixture(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    employee = UserProfile(cognito_sub="signed-contract-fixture", email="signed@example.invalid",
                           first_name="Empleado", last_name="Prueba", status="ACTIVE")
    db.add(employee)
    db.commit()
    db.refresh(employee)
    contract = EmployeeDocument(
        employee_id=employee.id,
        document_type="EMPLOYMENT_CONTRACT",
        original_filename="original.pdf",
        storage_key=f"training/employee-documents/{employee.id}/original.pdf",
        review_status="APPROVED",
        odoo_sign_status="PREPARED",
        odoo_sign_request_id=139,
        odoo_sign_request_status="SIGNED",
        odoo_sign_template_id=128,
        odoo_sign_source_key=f"training/employee-documents/{employee.id}/original.pdf",
    )
    db.add(contract)
    db.commit()
    db.refresh(contract)
    monkeypatch.setenv("ODOO_SIGN_STAGING_ARCHIVE_ENABLED", "true")
    monkeypatch.setenv("ODOO_SIGN_STAGING_TRACK_ENABLED", "true")
    monkeypatch.setenv("ODOO_SIGN_TEST_EMPLOYEE_IDS", employee.id)
    monkeypatch.setenv(
        "ODOO_SIGN_TEST_SIGNER_EMAILS",
        "employee@example.invalid,representative@example.invalid",
    )
    monkeypatch.setenv(
        "ODOO_SIGN_STAGING_SIGNED_ATTACHMENT_FIELD",
        "completed_document_attachment_id",
    )
    monkeypatch.setattr(
        sign_requests, "track",
        lambda db, employee_id, client: {"status": "SIGNED"},
    )
    try:
        yield db, employee, contract, monkeypatch
    finally:
        db.close()
        engine.dispose()


def test_signed_pdf_is_archived_separately_and_idempotently(fixture):
    db, employee, contract, monkeypatch = fixture
    saved = []
    def fake_archive(**kwargs):
        saved.append(kwargs)
        return {
            "key": f"training/employee-documents/{employee.id}/signed/139/sha.pdf",
            "sha256": hashlib.sha256(kwargs["payload"]).hexdigest(),
        }
    monkeypatch.setattr(signed_artifacts.storage, "archive_signed_contract_pdf", fake_archive)
    fake = FakeCompletedSign()
    result = signed_artifacts.archive(db, employee.id, client=fake)
    assert result["archived"] is True
    assert result["sha256"] == hashlib.sha256(PDF).hexdigest()
    assert saved[0]["payload"] == PDF
    assert contract.storage_key.endswith("/original.pdf")
    assert contract.odoo_sign_signed_attachment_id == 990
    assert all(action in ("fields_get", "search_read") for action, _ in fake.calls)
    assert signed_artifacts.archive(db, employee.id, client=fake) == result
    assert len(saved) == 1


@pytest.mark.parametrize("bad", [FakeCompletedSign(changed_field=True),
                                  FakeCompletedSign(mimetype="image/png")])
def test_archive_fails_closed_when_odoo_schema_or_mime_is_wrong(fixture, bad):
    db, employee, contract, monkeypatch = fixture
    monkeypatch.setattr(signed_artifacts.storage, "archive_signed_contract_pdf",
                        lambda **kw: pytest.fail("Never write invalid artifact"))
    with pytest.raises((signed_artifacts.ArchiveNotReady,
                        signed_artifacts.ArchiveUnavailable)):
        signed_artifacts.archive(db, employee.id, client=bad)
    assert contract.odoo_sign_signed_storage_key is None


def test_disabled_archive_cannot_contact_odoo(fixture, monkeypatch):
    db, employee, _, _ = fixture
    monkeypatch.delenv("ODOO_SIGN_STAGING_ARCHIVE_ENABLED")
    fake = FakeCompletedSign()
    with pytest.raises(signed_artifacts.ArchiveUnavailable, match="deshabilitada"):
        signed_artifacts.archive(db, employee.id, client=fake)
    assert fake.calls == []


def test_pending_signatures_cannot_be_archived(fixture, monkeypatch):
    db, employee, contract, _ = fixture
    monkeypatch.setattr(sign_requests, "track",
                        lambda db, employee_id, client: {"status": "PARTIALLY_SIGNED"})
    fake = FakeCompletedSign()
    with pytest.raises(signed_artifacts.ArchiveNotReady, match="Ambos firmantes"):
        signed_artifacts.archive(db, employee.id, client=fake)
    assert fake.calls == []
    assert contract.odoo_sign_signed_storage_key is None
