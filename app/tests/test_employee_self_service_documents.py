"""Employee self-service profile and requested document tests."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.db import Base
from app.domains.employee_documents import service
from app.models import UserProfile


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return engine, Session()


def _employee(db):
    employee = UserProfile(
        id="employee-self",
        cognito_sub="sub-self",
        email="laboral@asiati.com.co",
        first_name="Ana",
        last_name="Prueba",
        job_title="Analista",
        department="Tecnología",
        onboarding_status="PENDING",
        status="ACTIVE",
    )
    db.add(employee)
    db.commit()
    return employee


def test_employee_can_edit_personal_data_without_changing_work_fields():
    engine, db = _db()
    try:
        employee = _employee(db)
        result = service.update_own_profile(
            db,
            employee_id=employee.id,
            actor_sub="sub-self",
            changes={
                "first_name": "Andrea",
                "personal_email": "andrea@example.com",
                "phone": "+57 300 123 4567",
                "city": "Bogotá",
                "address": "Calle 1 # 2-3",
                "emergency_contact_name": "Familiar",
                "emergency_contact_phone": "+57 301 000 0000",
            },
        )

        assert result["first_name"] == "Andrea"
        assert result["personal_email"] == "andrea@example.com"
        assert result["phone"] == "+57 300 123 4567"
        assert result["job_title"] == "Analista"
        assert result["department"] == "Tecnología"
        assert result["work_email"] == "laboral@asiati.com.co"
    finally:
        db.close()
        engine.dispose()


def test_requested_document_upload_is_scoped_to_employee(monkeypatch):
    engine, db = _db()
    stored = {}
    try:
        employee = _employee(db)
        request = service.create_document_request(
            db,
            employee_id=employee.id,
            label="Documento de identidad",
            document_type="IDENTITY",
            required=True,
            requested_by_sub="admin-sub",
        )

        def fake_put(**kwargs):
            stored["payload"] = kwargs["payload"]
            return "employee-documents/test/document.pdf"

        monkeypatch.setattr(service.storage, "put_employee_document", fake_put)
        monkeypatch.setattr(service.storage, "delete_employee_document", lambda _key: None)
        monkeypatch.setattr(
            service.storage,
            "get_employee_document",
            lambda _key: (stored["payload"], "application/pdf"),
        )

        uploaded = service.upload_document(
            db,
            employee_id=employee.id,
            request_id=request["id"],
            filename="cedula.pdf",
            content_type="application/pdf",
            payload=b"%PDF-1.7 test",
            actor_sub="sub-self",
        )

        assert uploaded["status"] == "UPLOADED"
        assert uploaded["has_file"] is True
        assert uploaded["original_filename"] == "cedula.pdf"

        payload, filename, content_type = service.download_document(
            db,
            employee_id=employee.id,
            request_id=request["id"],
        )
        assert payload == b"%PDF-1.7 test"
        assert filename == "cedula.pdf"
        assert content_type == "application/pdf"
    finally:
        db.close()
        engine.dispose()


def test_document_upload_rejects_unsupported_format():
    engine, db = _db()
    try:
        employee = _employee(db)
        request = service.create_document_request(
            db,
            employee_id=employee.id,
            label="Documento",
            document_type=None,
            required=True,
            requested_by_sub="admin-sub",
        )
        try:
            service.upload_document(
                db,
                employee_id=employee.id,
                request_id=request["id"],
                filename="malware.exe",
                content_type="application/octet-stream",
                payload=b"MZ",
                actor_sub="sub-self",
            )
        except service.EmployeeSelfServiceError as exc:
            assert "Formato no permitido" in str(exc)
        else:
            raise AssertionError("unsupported upload should fail")
    finally:
        db.close()
        engine.dispose()
