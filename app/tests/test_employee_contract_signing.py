"""Contract PDF handoff to Odoo Sign staging: no mail or signing requests."""
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.domains.employee_documents import service, signing
from app.domains.employee_documents.models import EmployeeDocument
from app.models import UserProfile


class FakeOdooSign:
    def __init__(self, *, broken=False):
        self.created = []
        self.deleted = []
        self.broken = broken

    def fields_get(self, model):
        return {
            "sign.template": {"attachment_id": {}, "name": {}},
            "ir.attachment": {"datas": {}, "mimetype": {}},
        }[model]

    def create(self, model, values):
        self.created.append((model, values))
        if self.broken and model == "sign.template":
            raise RuntimeError("Sanitized mock failure")
        return 501 if model == "ir.attachment" else 812

    def unlink(self, model, ids):
        self.deleted.append((model, ids))
        return True


@pytest.fixture
def contract_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    employee = UserProfile(
        cognito_sub="sign-fixture",
        email="sign-fixture@example.invalid",
        first_name="Prueba",
        last_name="Firma",
        status="ACTIVE",
    )
    db.add(employee)
    db.commit()
    db.refresh(employee)
    contract = EmployeeDocument(
        employee_id=employee.id,
        document_type="EMPLOYMENT_CONTRACT",
        original_filename="contrato.pdf",
        content_type="application/pdf",
        size_bytes=18,
        storage_key=f"training/employee-documents/{employee.id}/contrato.pdf",
        review_status="APPROVED",
    )
    db.add(contract)
    db.commit()
    db.refresh(contract)
    monkeypatch.setenv("ODOO_SIGN_STAGING_PREPARE_ENABLED", "true")
    monkeypatch.setenv("ODOO_SIGN_TEST_EMPLOYEE_IDS", employee.id)
    monkeypatch.setattr(signing.staging, "staging_settings", lambda: SimpleNamespace(
        base_url="https://odoo-staging.example.invalid"
    ))
    monkeypatch.setattr(signing.storage, "read_employee_pdf_for_signing", lambda **kwargs: b"%PDF-1.7 fixture")
    yield db, employee, contract
    db.close()
    engine.dispose()


def test_only_allowlisted_employees_are_ready(contract_db, monkeypatch):
    db, employee, _contract = contract_db
    monkeypatch.setenv("ODOO_SIGN_TEST_EMPLOYEE_IDS", "someone-else")
    fake = FakeOdooSign()
    result = signing.readiness(db, employee.id, client=fake)
    assert result["ready"] is False
    with pytest.raises(signing.SignUnavailable, match="autorizado"):
        signing.prepare(db, employee.id, client=fake)
    assert fake.created == []


def test_not_enabled_never_calls_odoo(contract_db, monkeypatch):
    db, employee, _contract = contract_db
    monkeypatch.delenv("ODOO_SIGN_STAGING_PREPARE_ENABLED")
    fake = FakeOdooSign()
    assert signing.readiness(db, employee.id, client=fake)["ready"] is False
    with pytest.raises(signing.SignUnavailable, match="deshabilitada"):
        signing.prepare(db, employee.id, client=fake)
    assert fake.created == []


def test_staging_preparation_is_idempotent_and_does_not_send(contract_db, monkeypatch):
    db, employee, contract = contract_db
    fake = FakeOdooSign()
    result = signing.prepare(db, employee.id, client=fake)
    assert result["status"] == "PREPARED"
    assert result["ready"] is False
    assert result["template_url"].startswith("https://odoo-staging.example.invalid/web#")
    assert [model for model, _ in fake.created] == ["ir.attachment", "sign.template"]
    assert contract.odoo_sign_template_id == 812
    assert contract.odoo_sign_source_key == contract.storage_key
    again = signing.prepare(db, employee.id, client=fake)
    assert again == result
    assert len(fake.created) == 2
    monkeypatch.setattr(service.storage, "verify_document_object", lambda **kw: {
        "key": kw["key"],
        "content_type": kw["expected_content_type"],
        "size_bytes": kw["expected_size_bytes"],
    })
    with pytest.raises(ValueError, match="no se permite reemplazar"):
        service.finalize_upload(
            db,
            employee_id=employee.id,
            uploaded_by_sub="hr-admin",
            document_type="EMPLOYMENT_CONTRACT",
            filename="nuevo.pdf",
            key=f"training/employee-documents/{employee.id}/nuevo.pdf",
            content_type="application/pdf",
            size_bytes=100,
            admin_upload=True,
        )


def test_document_must_be_reviewed_pdf(contract_db):
    db, employee, contract = contract_db
    fake = FakeOdooSign()
    contract.review_status = "PENDING_REVIEW"
    db.commit()
    with pytest.raises(signing.SignNotReady, match="aprobado"):
        signing.prepare(db, employee.id, client=fake)
    assert fake.created == []
    contract.review_status = "APPROVED"
    contract.original_filename = "contrato.docx"
    contract.content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    db.commit()
    with pytest.raises(signing.SignNotReady, match="PDF"):
        signing.prepare(db, employee.id, client=fake)
    assert fake.created == []


def test_remote_failure_cleans_attachment_and_allows_retry(contract_db):
    db, employee, contract = contract_db
    fake = FakeOdooSign(broken=True)
    with pytest.raises(signing.SignUnavailable, match="No se pudo preparar"):
        signing.prepare(db, employee.id, client=fake)
    db.refresh(contract)
    assert contract.odoo_sign_status == "FAILED"
    assert contract.odoo_sign_template_id is None
    assert fake.deleted == [("ir.attachment", [501])]
    assert signing.prepare(db, employee.id, client=FakeOdooSign())["status"] == "PREPARED"
