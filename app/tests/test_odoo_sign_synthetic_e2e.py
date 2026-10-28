"""Integrated signature-first hiring gate with an entirely synthetic Odoo backend.

This is a state-machine regression, NOT a live Odoo staging or legal signature test.
It must never send invitations, use credentials or call real external services.
"""
from __future__ import annotations

import base64
import hashlib
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.domains.employee_documents import signed_artifacts, sign_requests, signing
from app.domains.employee_documents.models import ApplicationContract, EmployeeDocument
from app.domains.hiring import application_contracts, service as hiring_service
from app.models import Candidate, Job, JobCandidate, UserProfile


PDF = b"%PDF-1.7\n" + b"synthetic-test-data\n" * 12 + b"%%EOF\n"
EMPLOYEE_EMAIL = "empleado.adn360@example.invalid"
LEGAL_EMAIL = "representante.adn360@example.invalid"


class SyntheticSign:
    """Record every Odoo operation; prevent dispatch and unrelated writes."""

    def __init__(self):
        self.calls = []
        self.next_id = {"ir.attachment": 501, "sign.template": 812}
        self.overall_state = "sent"
        self.employee_state = "sent"
        self.representative_state = "sent"

    def fields_get(self, model):
        self.calls.append(("fields_get", model))
        fields = {
            "sign.template": {"attachment_id": {}, "name": {}},
            "ir.attachment": {
                name: {} for name in (
                    "id", "datas", "mimetype", "name", "file_size",
                    "res_model", "res_id",
                )
            },
            "sign.request": {
                "id": {}, "template_id": {}, "request_item_ids": {}, "state": {},
                "completed_document_attachment_ids": {
                    "type": "many2many", "relation": "ir.attachment",
                },
            },
            "sign.request.item": {
                name: {} for name in ("id", "role_id", "state", "signer_email")
            },
        }
        if model not in fields:
            raise AssertionError("Unexpected Odoo model: " + model)
        return fields[model]

    def create(self, model, values):
        self.calls.append(("create", model))
        if model not in self.next_id:
            raise AssertionError("Unexpected Odoo write: " + model)
        return self.next_id[model]

    def search_read(self, model, domain, *, fields, limit):
        self.calls.append(("search_read", model))
        if model == "sign.request":
            return [{
                "id": 139, "template_id": [812, "Plantilla sintética"],
                "request_item_ids": [301, 302], "state": self.overall_state,
                "completed_document_attachment_ids": [990, 991],
            }]
        if model == "sign.request.item":
            return [
                {
                    "id": 301, "role_id": [51, "Empleado"],
                    "signer_email": EMPLOYEE_EMAIL, "state": self.employee_state,
                },
                {
                    "id": 302, "role_id": [52, "Representante legal"],
                    "signer_email": LEGAL_EMAIL, "state": self.representative_state,
                },
            ]
        if model == "ir.attachment":
            def attachment(id_, name):
                return {
                    "id": id_, "name": name, "mimetype": "application/pdf",
                    "datas": base64.b64encode(PDF).decode("ascii"),
                    "res_model": "sign.request", "res_id": 139,
                    "file_size": len(PDF),
                }
            return [
                attachment(990, "contrato-ficticio.pdf"),
                attachment(991, "Certificate of completion - 2026-10-26.pdf"),
            ]
        raise AssertionError("Unexpected Odoo read: " + model)

    def assert_safe_writes(self):
        assert [model for kind, model in self.calls if kind == "create"] == [
            "ir.attachment", "sign.template",
        ]
        assert not any(kind in ("execute_kw", "unlink", "write") for kind, _ in self.calls)


@pytest.fixture
def synthetic_signing(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()

    job = Job(title="Vacante de pruebas", description="Ficticia", owner_sub="admin-test")
    candidate = Candidate(
        name="Persona Ficticia", email="candidate@example.invalid",
        owner_sub="admin-test",
    )
    profile = UserProfile(
        email=candidate.email, first_name="Persona", last_name="Ficticia",
        status="ACTIVE", onboarding_status="NOT_REQUIRED",
    )
    db.add_all([job, candidate, profile])
    db.flush()
    link = JobCandidate(
        job_id=job.id, candidate_id=candidate.id,
        employee_id=profile.id, application_status="OFFER",
    )
    document = EmployeeDocument(
        employee_id=profile.id, document_type="EMPLOYMENT_CONTRACT",
        review_status="APPROVED", original_filename="contrato-ficticio.pdf",
        content_type="application/pdf", size_bytes=len(PDF),
        storage_key=f"training/employee-documents/{profile.id}/contrato-ficticio.pdf",
    )
    db.add_all([link, document])
    db.commit()

    monkeypatch.setenv("ADN360_REQUIRE_SIGNED_CONTRACT_FOR_HIRE", "true")
    monkeypatch.setenv("ADN360_APPLICATION_CONTRACT_BINDING_ENABLED", "true")
    monkeypatch.setenv("ODOO_SIGN_PRODUCTION_ENABLED", "true")
    monkeypatch.setenv("ODOO_SIGN_PRODUCTION_ENABLED", "true")
    monkeypatch.setenv("ODOO_SIGN_PRODUCTION_ENABLED", "true")
    monkeypatch.setenv(
        "ODOO_SIGN_STAGING_SIGNED_ATTACHMENT_FIELD",
        "completed_document_attachment_ids",
    )
    monkeypatch.setattr(signing.sign_runtime, "signers", lambda db, document: (EMPLOYEE_EMAIL, LEGAL_EMAIL))
    monkeypatch.setenv("ODOO_SIGN_TEST_SIGNER_EMAILS", f"{EMPLOYEE_EMAIL},{LEGAL_EMAIL}")
    monkeypatch.setattr(
        application_contracts.company_catalog, "require_company",
        lambda company_id: {"id": company_id, "name": "Empresa ficticia"},
    )
    monkeypatch.setattr(
        signing.sign_runtime, "base_url",
        lambda: "https://odoo.example.test",
    )
    monkeypatch.setattr(
        signing.storage, "read_employee_pdf_for_signing",
        lambda **kwargs: PDF,
    )

    writes = []
    def store(kind, employee_id, request_id, payload):
        assert payload == PDF
        writes.append(kind)
        sha = hashlib.sha256(payload).hexdigest()
        suffix = "certificate/" if kind == "certificate" else ""
        return {
            "key": f"training/employee-documents/{employee_id}/signed/{request_id}/{suffix}{sha}.pdf",
            "sha256": sha,
        }
    monkeypatch.setattr(
        signed_artifacts.storage, "archive_signed_contract_pdf",
        lambda **kw: store("signed", **kw),
    )
    monkeypatch.setattr(
        signed_artifacts.storage, "archive_completion_certificate_pdf",
        lambda **kw: store("certificate", **kw),
    )
    fake = SyntheticSign()
    try:
        yield db, job, candidate, profile, link, document, fake, writes
    finally:
        db.close()
        engine.dispose()


def test_full_synthetic_signing_lifecycle_and_hiring_gate(synthetic_signing):
    db, job, candidate, profile, link, document, fake, writes = synthetic_signing
    def readiness():
        return hiring_service.hiring_signature_readiness(db, link=link)

    # Without the bound contract, no hire is allowed and Odoo is untouched.
    assert readiness()["status"] == "APPLICATION_CONTRACT_BINDING_REQUIRED"
    bound = application_contracts.bind(
        db, owner_sub="admin-test", job_id=job.id,
        candidate_id=candidate.id, odoo_company_id=97,
    )
    assert bound["bound"] is True
    assert readiness()["ready"] is False
    assert db.query(ApplicationContract).count() == 1

    prepared = signing.prepare(db, profile.id, client=fake)
    assert prepared["status"] == "PREPARED"
    assert document.odoo_sign_template_id == 812
    assert document.odoo_sign_environment == "production"
    original = document.storage_key
    assert readiness()["ready"] is False
    assert signing.prepare(db, profile.id, client=fake) == prepared
    fake.assert_safe_writes()

    # A single signature, or both signer states without an overall signed
    # request, must never grant hiring readiness or allow archive.
    partial = sign_requests.track(db, profile.id, request_id=139, client=fake)
    assert partial["status"] == "PENDING_SIGNATURE"
    fake.employee_state = "completed"
    assert sign_requests.track(db, profile.id, client=fake)["status"] == "PARTIALLY_SIGNED"
    with pytest.raises(signed_artifacts.ArchiveNotReady, match="Ambos firmantes"):
        signed_artifacts.archive(db, profile.id, client=fake)
    assert readiness()["ready"] is False

    fake.representative_state = "completed"
    assert sign_requests.track(db, profile.id, client=fake)["status"] != "SIGNED"
    fake.overall_state = "signed"
    assert sign_requests.track(db, profile.id, client=fake)["status"] == "SIGNED"
    assert readiness()["ready"] is False  # Signed is not yet archived.

    archived = signed_artifacts.archive(db, profile.id, client=fake)
    assert archived["archived"] is True
    assert archived["certificate_archived"] is True
    assert archived["sha256"] == hashlib.sha256(PDF).hexdigest()
    assert archived["certificate_sha256"] == hashlib.sha256(PDF).hexdigest()
    assert writes == ["signed", "certificate"]
    assert signed_artifacts.archive(db, profile.id, client=fake) == archived
    assert writes == ["signed", "certificate"]
    assert document.storage_key == original
    assert readiness()["status"] == "SIGNED_CONTRACT_ARCHIVED"
    assert readiness()["ready"] is True
    fake.assert_safe_writes()

    # The authorization is specific to the approved immutable source.
    document.storage_key = "training/employee-documents/tampered.pdf"
    db.commit()
    assert readiness()["ready"] is False


def test_no_staging_access_with_disabled_fixture(synthetic_signing, monkeypatch):
    db, job, candidate, profile, link, document, fake, writes = synthetic_signing
    monkeypatch.setenv("ODOO_SIGN_PRODUCTION_ENABLED", "false")
    with pytest.raises(signing.SignUnavailable, match="deshabilitada"):
        signing.prepare(db, profile.id, client=fake)
    assert fake.calls == []
    assert document.odoo_sign_template_id is None
    assert hiring_service.hiring_signature_readiness(db, link=link)["ready"] is False
