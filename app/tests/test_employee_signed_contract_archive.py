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
    def __init__(self, *, mimetype="application/pdf", changed_field=False,
                 missing_certificate=False, duplicate_contract=False,
                 wrong_request=False, corrupt_certificate=False,
                 extra_attachment=False):
        self.mimetype = mimetype
        self.changed_field = changed_field
        self.missing_certificate = missing_certificate
        self.duplicate_contract = duplicate_contract
        self.wrong_request = wrong_request
        self.corrupt_certificate = corrupt_certificate
        self.extra_attachment = extra_attachment
        self.calls = []

    def fields_get(self, model):
        self.calls.append(("fields_get", model))
        if model == "sign.request":
            return {"completed_document_attachment_ids": (
                {"type": "binary", "relation": None}
                if self.changed_field else
                {"type": "many2many", "relation": "ir.attachment"}
            )}
        if model == "ir.attachment":
            return {field: {} for field in (
                "id", "datas", "mimetype", "name", "file_size", "res_model", "res_id"
            )}
        raise AssertionError("Unexpected model")

    def search_read(self, model, domain, *, fields, limit):
        self.calls.append(("search_read", model))
        if model == "sign.request":
            ids = [990, 991]
            if self.missing_certificate:
                ids = [990]
            if self.extra_attachment:
                ids.append(992)
            return [{"id": 139, "completed_document_attachment_ids": ids}]
        if model == "ir.attachment":
            return [
                {"id": 990, "mimetype": self.mimetype, "name": "original.pdf",
                 "res_model": "sign.request", "res_id": 139, "file_size": len(PDF),
                 "datas": base64.b64encode(PDF).decode("ascii")},
                {"id": 991, "mimetype": "application/pdf",
                 "name": "original.pdf" if self.duplicate_contract else
                         "Certificate of completion - 2026-10-19 - 20:15:42.pdf",
                 "res_model": "sign.request",
                 "res_id": 138 if self.wrong_request else 139,
                 "file_size": len(PDF),
                 "datas": "NOT_BASE64" if self.corrupt_certificate else
                          base64.b64encode(PDF).decode("ascii")},
            ]
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
        odoo_sign_status="PREPARED", odoo_sign_environment="production",
        odoo_sign_request_id=139,
        odoo_sign_request_status="SIGNED",
        odoo_sign_template_id=128,
        odoo_sign_source_key=f"training/employee-documents/{employee.id}/original.pdf",
    )
    db.add(contract)
    db.commit()
    db.refresh(contract)
    monkeypatch.setenv("ODOO_SIGN_PRODUCTION_ENABLED", "true")
    monkeypatch.setenv("ODOO_SIGN_PRODUCTION_ENABLED", "true")
    monkeypatch.setenv("ODOO_SIGN_TEST_EMPLOYEE_IDS", employee.id)
    monkeypatch.setenv(
        "ODOO_SIGN_TEST_SIGNER_EMAILS",
        "employee@example.invalid,representative@example.invalid",
    )
    monkeypatch.setenv(
        "ODOO_SIGN_STAGING_SIGNED_ATTACHMENT_FIELD",
        "completed_document_attachment_ids",
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


def test_signed_pdf_and_certificate_are_archived_separately_and_idempotently(fixture):
    db, employee, contract, monkeypatch = fixture
    saved = []
    def fake_archive(**kwargs):
        saved.append(("signed", kwargs))
        return {
            "key": f"training/employee-documents/{employee.id}/signed/139/sha.pdf",
            "sha256": hashlib.sha256(kwargs["payload"]).hexdigest(),
        }
    def fake_certificate(**kwargs):
        saved.append(("certificate", kwargs))
        return {
            "key": f"training/employee-documents/{employee.id}/signed/139/certificate/sha.pdf",
            "sha256": hashlib.sha256(kwargs["payload"]).hexdigest(),
        }
    monkeypatch.setattr(signed_artifacts.storage, "archive_signed_contract_pdf", fake_archive)
    monkeypatch.setattr(signed_artifacts.storage, "archive_completion_certificate_pdf", fake_certificate)
    fake = FakeCompletedSign()
    result = signed_artifacts.archive(db, employee.id, client=fake)
    assert result["archived"] is True
    assert result["certificate_archived"] is True
    assert result["sha256"] == hashlib.sha256(PDF).hexdigest()
    assert result["certificate_sha256"] == hashlib.sha256(PDF).hexdigest()
    assert [kind for kind, _ in saved] == ["signed", "certificate"]
    assert all(row["payload"] == PDF for _, row in saved)
    assert contract.storage_key.endswith("/original.pdf")
    assert contract.odoo_sign_signed_attachment_id == 990
    assert contract.odoo_sign_certificate_attachment_id == 991
    assert all(action in ("fields_get", "search_read") for action, _ in fake.calls)
    assert signed_artifacts.archive(db, employee.id, client=fake) == result
    assert len(saved) == 2


@pytest.mark.parametrize("bad", [FakeCompletedSign(changed_field=True),
                                  FakeCompletedSign(mimetype="image/png")])
def test_archive_fails_closed_when_odoo_schema_or_mime_is_wrong(fixture, bad):
    db, employee, contract, monkeypatch = fixture
    monkeypatch.setattr(signed_artifacts.storage, "archive_signed_contract_pdf",
                        lambda **kw: pytest.fail("Never write invalid artifact"))
    monkeypatch.setattr(signed_artifacts.storage, "archive_completion_certificate_pdf",
                        lambda **kw: pytest.fail("Never write invalid artifact"))
    with pytest.raises((signed_artifacts.ArchiveNotReady,
                        signed_artifacts.ArchiveUnavailable)):
        signed_artifacts.archive(db, employee.id, client=bad)
    assert contract.odoo_sign_signed_storage_key is None


@pytest.mark.parametrize("bad", [
    FakeCompletedSign(missing_certificate=True),
    FakeCompletedSign(duplicate_contract=True),
    FakeCompletedSign(wrong_request=True),
    FakeCompletedSign(corrupt_certificate=True),
    FakeCompletedSign(extra_attachment=True),
])
def test_archive_rejects_missing_ambiguous_foreign_or_corrupt_certificates(fixture, bad):
    db, employee, contract, monkeypatch = fixture
    monkeypatch.setattr(signed_artifacts.storage, "archive_signed_contract_pdf",
                        lambda **kw: pytest.fail("Never store an unverified pair"))
    with pytest.raises(signed_artifacts.ArchiveNotReady):
        signed_artifacts.archive(db, employee.id, client=bad)
    assert contract.odoo_sign_signed_storage_key is None
    assert contract.odoo_sign_certificate_storage_key is None


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


def test_private_archive_uses_content_hash_and_never_replaces_original(monkeypatch):
    from app.infrastructure.storage import employee_documents as storage
    stored = []
    monkeypatch.setattr(storage, "get_training_content_bucket", lambda: "private-bucket")
    monkeypatch.setattr(storage, "_s3_client", lambda: type("S3", (), {
        "put_object": lambda self, **kw: stored.append(kw)
    })())
    result = storage.archive_signed_contract_pdf(
        employee_id="fixture-1", request_id=139, payload=PDF,
    )
    assert result["sha256"] == hashlib.sha256(PDF).hexdigest()
    assert result["key"].startswith("training/employee-documents/fixture-1/signed/139/")
    assert stored[0]["Body"] == PDF
    assert stored[0]["ServerSideEncryption"] == "AES256"
    assert stored[0]["Metadata"]["odoo-sign-request-id"] == "139"
    assert stored[0]["Metadata"]["odoo-sign-artifact"] == "signed-contract"
    cert = storage.archive_completion_certificate_pdf(
        employee_id="fixture-1", request_id=139, payload=PDF,
    )
    assert cert["sha256"] == hashlib.sha256(PDF).hexdigest()
    assert "/signed/139/certificate/" in cert["key"]
    assert stored[1]["ServerSideEncryption"] == "AES256"
    assert stored[1]["Metadata"]["odoo-sign-artifact"] == "certificate"


@pytest.mark.parametrize("request_id,payload", [
    (0, PDF), (-1, PDF), (True, PDF),
    (139, b""), (139, b"FAKE" * 100), (139, b"%PDF-" + b"a" * 110),
])
def test_reject_unsupported_signed_pdf_before_storage(request_id, payload, monkeypatch):
    from app.infrastructure.storage import employee_documents as storage
    monkeypatch.setattr(storage, "_s3_client",
                        lambda: pytest.fail("Rejected bytes must not hit S3"))
    with pytest.raises(ValueError):
        storage.archive_signed_contract_pdf(
            employee_id="fixture", request_id=request_id, payload=payload,
        )


def test_archived_pdf_status_and_download_return_only_the_signed_key(fixture, monkeypatch):
    db, employee, contract, _ = fixture
    assert signed_artifacts.status(db, employee.id)["archived"] is False
    with pytest.raises(signed_artifacts.ArchiveNotReady):
        signed_artifacts.download(db, employee.id)
    contract.odoo_sign_signed_storage_key = "training/employee-documents/signed-id/signed/139/file.pdf"
    contract.odoo_sign_signed_sha256 = "c" * 64
    contract.odoo_sign_certificate_storage_key = "training/employee-documents/signed-id/signed/139/certificate/file.pdf"
    contract.odoo_sign_certificate_sha256 = "d" * 64
    db.commit()
    requested = []
    monkeypatch.setattr(signed_artifacts.storage, "create_document_download_url",
                        lambda key, filename: requested.append(key) or "https://example.invalid/file")
    link = signed_artifacts.download(db, employee.id)
    assert link["url"] == "https://example.invalid/file"
    certificate_link = signed_artifacts.download_certificate(db, employee.id)
    assert certificate_link["url"] == "https://example.invalid/file"
    assert requested == [
        contract.odoo_sign_signed_storage_key,
        contract.odoo_sign_certificate_storage_key,
    ]
    assert signed_artifacts.status(db, employee.id)["archived"] is True
    assert signed_artifacts.status(db, employee.id)["certificate_sha256"] == "d" * 64


def test_unverified_signed_attachment_relation_cannot_be_archived(fixture, monkeypatch):
    db, employee, contract, _ = fixture
    monkeypatch.setenv("ODOO_SIGN_STAGING_SIGNED_ATTACHMENT_FIELD", "attachment_id")
    with pytest.raises(signed_artifacts.ArchiveUnavailable, match="campo"):
        signed_artifacts.archive(db, employee.id, client=FakeCompletedSign())
    assert contract.odoo_sign_signed_storage_key is None


def test_missing_or_ambiguous_remote_signed_attachment_fails_closed(fixture, monkeypatch):
    db, employee, contract, _ = fixture
    fake = FakeCompletedSign()
    original = fake.search_read
    def remote(model, domain, *, fields, limit):
        if model == "sign.request":
            return [{"id": 139, "completed_document_attachment_ids": False}]
        return original(model, domain, fields=fields, limit=limit)
    fake.search_read = remote
    with pytest.raises(signed_artifacts.ArchiveNotReady):
        signed_artifacts.archive(db, employee.id, client=fake)
    assert contract.odoo_sign_signed_storage_key is None
