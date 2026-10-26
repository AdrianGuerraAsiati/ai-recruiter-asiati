"""Regression tests for application-scoped contract binding and Sign preparation."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.domains.employee_documents.models import ApplicationContract, EmployeeDocument
from app.domains.employee_documents import signing
from app.domains.hiring import application_contracts
from app.domains.hiring import router as hiring_router
from app.domains.hiring import service as hiring_service
from app.models import Candidate, Job, JobCandidate, UserProfile


class FakeOdooSchema:
    def __init__(self):
        self.calls = []

    def fields_get(self, model):
        self.calls.append(("fields_get", model))
        if model == "sign.template":
            return {"attachment_id": {}, "name": {}}
        if model == "ir.attachment":
            return {"datas": {}, "mimetype": {}}
        raise AssertionError(f"Unexpected Odoo model: {model}")


@pytest.fixture
def binding_context():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    job = Job(
        title="Desarrollador de prueba",
        description="Vacante ficticia para pruebas de contrato",
        owner_sub="admin-sub",
        country_code="CO",
        company_name="ASIATI Colombia",
        city="Bogotá",
    )
    candidate = Candidate(
        name="Candidata Prueba",
        email="candidate@example.invalid",
        owner_sub="admin-sub",
        metadata_={},
        is_banned=False,
    )
    profile = UserProfile(
        email="candidate@example.invalid",
        first_name="Candidata",
        last_name="Prueba",
        status="ACTIVE",
    )
    db.add_all([job, candidate, profile])
    db.flush()
    link = JobCandidate(
        job_id=job.id,
        candidate_id=candidate.id,
        employee_id=profile.id,
        application_status="SELECTED",
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    yield db, job, candidate, profile, link
    db.close()
    engine.dispose()


def approved_unsigned_contract(db, profile):
    document = EmployeeDocument(
        employee_id=profile.id,
        document_type="EMPLOYMENT_CONTRACT",
        original_filename="contrato-prueba.pdf",
        content_type="application/pdf",
        size_bytes=128,
        storage_key=f"contracts/{profile.id}/approved.pdf",
        review_status="APPROVED",
        odoo_sign_status="NOT_PREPARED",
        odoo_sign_request_status="UNLINKED",
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def test_binding_status_requires_applicant_profile(binding_context, monkeypatch):
    db, job, candidate, _, link = binding_context
    monkeypatch.setenv("ADN360_APPLICATION_CONTRACT_BINDING_ENABLED", "true")
    link.employee_id = None
    db.commit()

    result = application_contracts.binding_status(
        db, owner_sub="admin-sub", job_id=job.id, candidate_id=candidate.id,
    )

    assert result["enabled"] is True
    assert result["bound"] is False
    assert result["can_bind"] is False
    assert result["status"] == "APPLICANT_PROFILE_REQUIRED"


def test_binding_status_requires_approved_pdf(binding_context, monkeypatch):
    db, job, candidate, profile, _ = binding_context
    monkeypatch.setenv("ADN360_APPLICATION_CONTRACT_BINDING_ENABLED", "true")
    document = approved_unsigned_contract(db, profile)
    document.review_status = "PENDING_REVIEW"
    db.commit()

    result = application_contracts.binding_status(
        db, owner_sub="admin-sub", job_id=job.id, candidate_id=candidate.id,
    )

    assert result["bound"] is False
    assert result["can_bind"] is False
    assert result["status"] == "CONTRACT_NOT_APPROVED"


def test_binding_status_allows_approved_unsigned_pdf(binding_context, monkeypatch):
    db, job, candidate, profile, _ = binding_context
    monkeypatch.setenv("ADN360_APPLICATION_CONTRACT_BINDING_ENABLED", "true")
    approved_unsigned_contract(db, profile)

    result = application_contracts.binding_status(
        db, owner_sub="admin-sub", job_id=job.id, candidate_id=candidate.id,
    )

    assert result["enabled"] is True
    assert result["bound"] is False
    assert result["can_bind"] is True
    assert result["status"] == "CONTRACT_READY_TO_BIND"


def test_binding_status_reports_existing_binding_and_detects_source_change(binding_context, monkeypatch):
    db, job, candidate, profile, link = binding_context
    monkeypatch.setenv("ADN360_APPLICATION_CONTRACT_BINDING_ENABLED", "true")
    document = approved_unsigned_contract(db, profile)
    db.add(ApplicationContract(
        application_id=link.id,
        employee_id=profile.id,
        document_id=document.id,
        odoo_company_id=23,
        source_storage_key=document.storage_key,
    ))
    db.commit()

    result = application_contracts.binding_status(
        db, owner_sub="admin-sub", job_id=job.id, candidate_id=candidate.id,
    )
    assert result["bound"] is True
    assert result["valid"] is True
    assert result["odoo_company_id"] == 23
    assert result["status"] == "APPLICATION_CONTRACT_BOUND"

    document.storage_key = "contracts/replaced.pdf"
    db.commit()
    result = application_contracts.binding_status(
        db, owner_sub="admin-sub", job_id=job.id, candidate_id=candidate.id,
    )
    assert result["bound"] is True
    assert result["valid"] is False
    assert result["can_bind"] is False
    assert result["status"] == "APPLICATION_CONTRACT_BINDING_INVALID"


def test_binding_route_exposes_status_and_capability(binding_context, monkeypatch):
    db, job, candidate, profile, _ = binding_context
    monkeypatch.setenv("ADN360_APPLICATION_CONTRACT_BINDING_ENABLED", "true")
    approved_unsigned_contract(db, profile)

    result = hiring_router.get_application_contract_binding(
        job_id=job.id, candidate_id=candidate.id, db=db,
        principal={"sub": "admin-sub"},
    )
    assert result["status"] == "CONTRACT_READY_TO_BIND"
    assert result["can_bind"] is True

    monkeypatch.setattr(hiring_service, "signed_contract_hiring_gate_enabled", lambda: False)
    monkeypatch.setattr(application_contracts, "binding_enabled", lambda: True)
    capabilities = hiring_router.signature_hiring_flow_capabilities(_principal={})
    assert capabilities["enabled"] is False
    assert capabilities["binding_enabled"] is True


def test_sign_readiness_blocks_unbound_contract_before_odoo_calls(binding_context, monkeypatch):
    db, _, _, profile, _ = binding_context
    document = approved_unsigned_contract(db, profile)
    monkeypatch.setenv("ADN360_APPLICATION_CONTRACT_BINDING_ENABLED", "true")
    monkeypatch.setenv("ODOO_SIGN_STAGING_PREPARE_ENABLED", "true")
    monkeypatch.setenv("ODOO_SIGN_TEST_EMPLOYEE_IDS", profile.id)
    client = FakeOdooSchema()

    result = signing.readiness(db, profile.id, client=client)

    assert result["ready"] is False
    assert "vincula" in result["message"].lower()
    assert client.calls == []
    assert document.odoo_sign_status == "NOT_PREPARED"


def test_sign_prepare_blocks_unbound_contract_before_any_mutation(binding_context, monkeypatch):
    db, _, _, profile, _ = binding_context
    document = approved_unsigned_contract(db, profile)
    monkeypatch.setenv("ADN360_APPLICATION_CONTRACT_BINDING_ENABLED", "true")
    monkeypatch.setenv("ODOO_SIGN_STAGING_PREPARE_ENABLED", "true")
    monkeypatch.setenv("ODOO_SIGN_TEST_EMPLOYEE_IDS", profile.id)
    client = FakeOdooSchema()

    with pytest.raises(signing.SignNotReady, match="vincula"):
        signing.prepare(db, profile.id, client=client)

    assert client.calls == []
    assert document.odoo_sign_status == "NOT_PREPARED"


def test_sign_readiness_accepts_matching_binding_and_keeps_legacy_flag_off(binding_context, monkeypatch):
    db, _, _, profile, link = binding_context
    document = approved_unsigned_contract(db, profile)
    monkeypatch.setenv("ADN360_APPLICATION_CONTRACT_BINDING_ENABLED", "true")
    monkeypatch.setenv("ODOO_SIGN_STAGING_PREPARE_ENABLED", "true")
    monkeypatch.setenv("ODOO_SIGN_TEST_EMPLOYEE_IDS", profile.id)
    db.add(ApplicationContract(
        application_id=link.id,
        employee_id=profile.id,
        document_id=document.id,
        odoo_company_id=23,
        source_storage_key=document.storage_key,
    ))
    db.commit()
    client = FakeOdooSchema()

    result = signing.readiness(db, profile.id, client=client)

    assert result["ready"] is True
    assert client.calls == [("fields_get", "sign.template"), ("fields_get", "ir.attachment")]

    monkeypatch.delenv("ADN360_APPLICATION_CONTRACT_BINDING_ENABLED")
    client = FakeOdooSchema()
    result = signing.readiness(db, profile.id, client=client)
    assert result["ready"] is True


def test_binding_rejects_non_pdf_contract(binding_context, monkeypatch):
    db, job, candidate, profile, _ = binding_context
    monkeypatch.setenv("ADN360_APPLICATION_CONTRACT_BINDING_ENABLED", "true")
    monkeypatch.setattr(
        application_contracts.company_catalog,
        "require_company",
        lambda company_id: {"id": company_id, "name": "ASIATI Colombia"},
    )
    document = approved_unsigned_contract(db, profile)
    document.content_type = "application/msword"
    document.original_filename = "contrato.doc"
    db.commit()

    result = application_contracts.binding_status(
        db, owner_sub="admin-sub", job_id=job.id, candidate_id=candidate.id,
    )
    assert result["status"] == "CONTRACT_NOT_PDF"
    assert result["can_bind"] is False

    with pytest.raises(application_contracts.ContractBindingConflict, match="PDF"):
        application_contracts.bind(
            db, owner_sub="admin-sub", job_id=job.id, candidate_id=candidate.id,
            odoo_company_id=23,
        )
    assert db.query(ApplicationContract).count() == 0
