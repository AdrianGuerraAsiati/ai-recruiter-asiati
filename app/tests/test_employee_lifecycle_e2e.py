"""Lifecycle E2E contract: create employee -> documents -> onboarding."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.access_control import ADMIN, EMPLOYEE, ensure_rbac_catalog
from app.db import Base
from app.domains.employee_documents import router as documents_router
from app.domains.employee_documents import service as documents_service
from app.domains.employee_documents.schemas import (
    CreateEmployeeDocumentUploadRequest,
    FinalizeEmployeeDocumentUploadRequest,
)
from app.domains.employees import router as employees_router
from app.domains.employees import service as employees_service
from app.domains.employees.schemas import CreateEmployeeRequest
from app.domains.training import router as training_router
from app.models import TrainingAssignment, UserProfile


class FakeCognitoClient:
    def admin_create_user(self, **kwargs):
        email = kwargs["Username"]
        return {
            "User": {
                "Username": email,
                "Attributes": [
                    {"Name": "sub", "Value": f"sub-{email}"},
                    {"Name": "email", "Value": email},
                ],
            }
        }

    def admin_get_user(self, **kwargs):
        email = kwargs["Username"]
        return {
            "Username": email,
            "UserAttributes": [
                {"Name": "sub", "Value": f"sub-{email}"},
                {"Name": "email", "Value": email},
            ],
        }

    def admin_delete_user(self, **kwargs):
        return None


def test_employee_creation_document_upload_and_onboarding(monkeypatch):
    monkeypatch.setenv("COGNITO_USER_POOL_ID", "pool-e2e")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    ensure_rbac_catalog(db)
    db.commit()

    monkeypatch.setattr(
        employees_service,
        "get_admin_cognito_client",
        lambda: FakeCognitoClient(),
    )

    admin_principal = {
        "sub": "admin-sub",
        "roles": [ADMIN],
        "permissions": [],
        "profile": {"id": "admin-id"},
    }
    created = employees_router.create_employee(
        CreateEmployeeRequest(
            username="e2e.employee",
            email="e2e.employee@asiati.com.co",
            first_name="E2E",
            last_name="Employee",
            job_title="Desarrollador",
            department="Tecnología",
            country_code="CO",
            company_name="ASIATI",
            role=EMPLOYEE,
        ),
        db=db,
        principal=admin_principal,
    )

    employee_id = created["employee"]["id"]
    employee = db.query(UserProfile).filter(UserProfile.id == employee_id).one()
    assert created["credentials"]["must_change_password"] is True
    assert created["credentials"]["username"] == "e2e.employee"
    assert employee.cognito_sub == "sub-e2e.employee@asiati.com.co"
    assert employee.onboarding_status == "PENDING"
    assert db.query(TrainingAssignment).filter(
        TrainingAssignment.employee_id == employee_id
    ).count() == 1

    employee_principal = {
        "sub": employee.cognito_sub,
        "roles": [EMPLOYEE],
        "permissions": [
            "employee_documents.read_own",
            "employee_documents.upload_own",
            "training.read",
            "training.consume",
        ],
        "profile": {"id": employee.id, "status": "ACTIVE"},
    }

    monkeypatch.setattr(
        documents_service.storage,
        "create_document_upload",
        lambda **kwargs: {
            "key": f"employees/documents/{employee.id}/e2e-cedula.pdf",
            "upload": {
                "url": "https://s3.example/upload",
                "fields": {"key": f"employees/documents/{employee.id}/e2e-cedula.pdf"},
            },
            "expires_in": 3600,
            "max_size_bytes": 15 * 1024 * 1024,
        },
    )
    monkeypatch.setattr(
        documents_service.storage,
        "verify_document_object",
        lambda **kwargs: {
            "key": kwargs["key"],
            "content_type": kwargs["expected_content_type"],
            "size_bytes": kwargs["expected_size_bytes"],
        },
    )

    upload = documents_router.create_my_document_upload(
        CreateEmployeeDocumentUploadRequest(
            document_type="IDENTITY",
            filename="cedula.pdf",
            content_type="application/pdf",
            size_bytes=512,
        ),
        db=db,
        principal=employee_principal,
    )
    assert upload["key"].startswith(f"employees/documents/{employee.id}/")

    stored = documents_router.complete_my_document_upload(
        FinalizeEmployeeDocumentUploadRequest(
            document_type="IDENTITY",
            filename="cedula.pdf",
            content_type="application/pdf",
            size_bytes=512,
            key=upload["key"],
        ),
        db=db,
        principal=employee_principal,
    )
    assert stored["employee_id"] == employee.id
    assert stored["original_filename"] == "cedula.pdf"

    my_documents = documents_router.my_documents(db=db, principal=employee_principal)
    assert my_documents["total"] == 1
    assert my_documents["items"][0]["document_type"] == "IDENTITY"

    onboarding = training_router.my_training(db=db, principal=employee_principal)
    assert onboarding["total"] == 1
    assert onboarding["items"][0]["course"]["is_onboarding"] is True
    assert onboarding["items"][0]["course"]["progress_percent"] == 0

    db.close()
    engine.dispose()
