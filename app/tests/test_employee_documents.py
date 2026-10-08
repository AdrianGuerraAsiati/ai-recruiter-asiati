"""Employee document domain tests."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.access_control import EMPLOYEE, ROLE_PERMISSION_MATRIX
from app.db import Base
from app.domains.employee_documents import service
from app.domains.employee_documents.models import EmployeeDocument
from app.models import UserProfile


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return engine, Session()


def _employee(db, email="employee@asiati.com.co"):
    employee = UserProfile(
        cognito_sub=f"sub-{email}",
        email=email,
        first_name="Ana",
        last_name="Pérez",
        status="ACTIVE",
    )
    db.add(employee)
    db.commit()
    db.refresh(employee)
    return employee


def test_employee_role_can_read_and_upload_own_documents():
    permissions = ROLE_PERMISSION_MATRIX[EMPLOYEE]
    assert "employee_documents.read_own" in permissions
    assert "employee_documents.upload_own" in permissions
    assert "employee_documents.read_all" not in permissions


def test_finalize_document_replaces_same_type_without_duplicate(monkeypatch):
    engine, db = _db()
    employee = _employee(db)
    deleted = []

    monkeypatch.setattr(
        service.storage,
        "verify_document_object",
        lambda **kwargs: {
            "key": kwargs["key"],
            "content_type": kwargs["expected_content_type"],
            "size_bytes": kwargs["expected_size_bytes"],
        },
    )
    monkeypatch.setattr(
        service.storage,
        "delete_document_object",
        lambda key: deleted.append(key),
    )

    first = service.finalize_upload(
        db,
        employee_id=employee.id,
        uploaded_by_sub=employee.cognito_sub,
        document_type="IDENTITY",
        filename="cedula.pdf",
        key=f"employees/documents/{employee.id}/first-cedula.pdf",
        content_type="application/pdf",
        size_bytes=100,
    )
    second = service.finalize_upload(
        db,
        employee_id=employee.id,
        uploaded_by_sub=employee.cognito_sub,
        document_type="IDENTITY",
        filename="cedula-nueva.pdf",
        key=f"employees/documents/{employee.id}/second-cedula.pdf",
        content_type="application/pdf",
        size_bytes=150,
    )

    assert first.id == second.id
    assert db.query(EmployeeDocument).count() == 1
    assert second.original_filename == "cedula-nueva.pdf"
    assert deleted == [f"employees/documents/{employee.id}/first-cedula.pdf"]

    db.close()
    engine.dispose()


def test_download_payload_uses_private_presigned_url(monkeypatch):
    engine, db = _db()
    employee = _employee(db)
    document = EmployeeDocument(
        employee_id=employee.id,
        document_type="BANK_CERTIFICATE",
        original_filename="banco.pdf",
        storage_key=f"employees/documents/{employee.id}/banco.pdf",
        content_type="application/pdf",
        size_bytes=200,
        uploaded_by_sub=employee.cognito_sub,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    monkeypatch.setattr(
        service.storage,
        "create_document_download_url",
        lambda key, filename: f"https://private.example/{filename}?signed=1",
    )

    payload = service.download_payload(db, document.id)

    assert payload["url"].startswith("https://private.example/")
    assert payload["filename"] == "banco.pdf"
    assert "storage_key" not in service.document_payload(document)

    db.close()
    engine.dispose()


class FakeS3:
    def __init__(self):
        self.posts = []
        self.head = {
            "ContentLength": 321,
            "ContentType": "application/pdf",
        }
        self.urls = []
        self.deleted = []

    def generate_presigned_post(self, **kwargs):
        self.posts.append(kwargs)
        return {"url": "https://s3.example/upload", "fields": {"key": kwargs["Key"]}}

    def head_object(self, **kwargs):
        return dict(self.head)

    def generate_presigned_url(self, operation, Params, ExpiresIn):
        self.urls.append((operation, Params, ExpiresIn))
        return "https://s3.example/download?signed=1"

    def delete_object(self, **kwargs):
        self.deleted.append(kwargs)


def test_storage_presigned_upload_verify_download_and_delete(monkeypatch):
    from app.infrastructure.storage import employee_documents as storage

    fake = FakeS3()
    monkeypatch.setattr(storage, "_s3_client", lambda: fake)
    monkeypatch.setattr(storage, "get_training_content_bucket", lambda: "private-bucket")

    upload = storage.create_document_upload(
        employee_id="employee-1",
        filename="cedula.pdf",
        content_type="application/pdf",
        size_bytes=321,
    )

    assert upload["key"].startswith("employees/documents/employee-1/")
    assert upload["key"].endswith("-cedula.pdf")
    assert fake.posts[0]["Bucket"] == "private-bucket"
    assert fake.posts[0]["Conditions"][-1] == ["content-length-range", 321, 321]

    verified = storage.verify_document_object(
        employee_id="employee-1",
        key=upload["key"],
        expected_content_type="application/pdf",
        expected_size_bytes=321,
    )
    assert verified == {
        "key": upload["key"],
        "content_type": "application/pdf",
        "size_bytes": 321,
    }

    url = storage.create_document_download_url(
        upload["key"],
        filename="cedula.pdf",
    )
    assert url == "https://s3.example/download?signed=1"
    assert fake.urls[0][0] == "get_object"
    assert fake.urls[0][1]["ResponseContentDisposition"] == 'attachment; filename="cedula.pdf"'

    storage.delete_document_object(upload["key"])
    assert fake.deleted == [{"Bucket": "private-bucket", "Key": upload["key"]}]


@pytest.mark.parametrize(
    ("filename", "content_type", "size_bytes", "message"),
    [
        ("cedula.exe", "application/octet-stream", 100, "Formato no soportado"),
        ("cedula.jpg", "image/jpeg", 0, "máximo 15 MB"),
        ("cedula.png", "image/jpeg", 100, "extensión"),
    ],
)
def test_storage_rejects_invalid_uploads(filename, content_type, size_bytes, message):
    from app.infrastructure.storage import employee_documents as storage

    with pytest.raises(ValueError, match=message):
        storage.create_document_upload(
            employee_id="employee-1",
            filename=filename,
            content_type=content_type,
            size_bytes=size_bytes,
        )


def test_storage_verify_rejects_foreign_employee_key():
    from app.infrastructure.storage import employee_documents as storage

    with pytest.raises(ValueError, match="no pertenece"):
        storage.verify_document_object(
            employee_id="employee-1",
            key="employees/documents/employee-2/cedula.pdf",
            expected_content_type="application/pdf",
            expected_size_bytes=321,
        )
