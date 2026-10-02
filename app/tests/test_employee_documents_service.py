"""Domain coverage for immutable employee signed documents."""

from datetime import datetime, timezone
import hashlib

import fitz
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.domains.employee_documents import service
from app.domains.employee_documents.storage import EmployeeDocumentStorageConfig
from app.models import (
    EmployeeDocument,
    EmployeeDocumentArtifact,
    EmployeeDocumentVersion,
    OdooContractSync,
    UserProfile,
)


class FakeStorage:
    def __init__(self, *, max_upload_bytes=15 * 1024 * 1024):
        self.config = EmployeeDocumentStorageConfig(
            bucket="employee-documents-test",
            max_upload_bytes=max_upload_bytes,
        )
        self.objects = {}
        self.put_calls = []
        self.delete_calls = []

    def put_bytes(self, key, body, content_type):
        self.put_calls.append((key, body, content_type))
        self.objects[key] = bytes(body)

    def delete_object(self, key):
        self.delete_calls.append(key)
        self.objects.pop(key, None)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            UserProfile.__table__,
            OdooContractSync.__table__,
            EmployeeDocument.__table__,
            EmployeeDocumentArtifact.__table__,
            EmployeeDocumentVersion.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    session = Session()
    employee = UserProfile(
        id="employee-1",
        cognito_sub="employee-sub-1",
        email="employee1@asiati.com.co",
        first_name="Ana",
        last_name="Pérez",
        status="ACTIVE",
    )
    session.add(employee)
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _pdf_bytes():
    document = fitz.open()
    document.new_page()
    data = document.tobytes()
    document.close()
    return data


def _document(db):
    return service.create_document(
        db,
        employee_id="employee-1",
        document_type="CONTRACT",
        title="Contrato laboral",
        created_by_sub="admin-sub",
    )


def test_second_signed_upload_creates_v2_without_mutating_v1(db):
    document = _document(db)
    storage = FakeStorage()
    pdf_v1 = _pdf_bytes()
    pdf_v2 = _pdf_bytes() + b"\n% correction marker"

    first = service.append_signed_version(
        db,
        employee_id="employee-1",
        document_id=document.id,
        file_bytes=pdf_v1,
        original_filename="contrato-v1.pdf",
        uploaded_by_sub="admin-sub",
        signed_at=datetime(2026, 10, 2, tzinfo=timezone.utc),
        storage=storage,
    )
    first_key = first.storage_key
    first_hash = first.sha256

    second = service.append_signed_version(
        db,
        employee_id="employee-1",
        document_id=document.id,
        file_bytes=pdf_v2,
        original_filename="contrato-v2.pdf",
        uploaded_by_sub="admin-sub",
        signed_at=datetime(2026, 10, 3, tzinfo=timezone.utc),
        storage=storage,
    )

    db.refresh(first)
    db.refresh(document)
    assert first.version_number == 1
    assert second.version_number == 2
    assert first.storage_key == first_key
    assert first.sha256 == first_hash
    assert first.storage_key != second.storage_key
    assert first.superseded_by_version_id == second.id
    assert first.superseded_at is not None
    assert document.current_signed_version_id == second.id
    assert document.status == "SIGNED"
    assert storage.objects[first.storage_key] == pdf_v1
    assert storage.objects[second.storage_key] == pdf_v2


def test_spoofed_pdf_is_rejected_before_storage(db):
    document = _document(db)
    storage = FakeStorage()

    with pytest.raises(service.EmployeeDocumentValidationError):
        service.append_signed_version(
            db,
            employee_id="employee-1",
            document_id=document.id,
            file_bytes=b"%PDF-not-a-real-document",
            original_filename="signed.pdf",
            uploaded_by_sub="admin-sub",
            signed_at=None,
            storage=storage,
        )

    assert storage.put_calls == []
    assert db.query(EmployeeDocumentVersion).count() == 0


def test_oversized_pdf_is_rejected_before_storage(db):
    document = _document(db)
    pdf = _pdf_bytes()
    storage = FakeStorage(max_upload_bytes=len(pdf) - 1)

    with pytest.raises(service.EmployeeDocumentValidationError):
        service.append_signed_version(
            db,
            employee_id="employee-1",
            document_id=document.id,
            file_bytes=pdf,
            original_filename="signed.pdf",
            uploaded_by_sub="admin-sub",
            signed_at=None,
            storage=storage,
        )

    assert storage.put_calls == []


def test_empty_pdf_is_rejected_before_storage(db):
    document = _document(db)
    storage = FakeStorage()

    with pytest.raises(service.EmployeeDocumentValidationError):
        service.append_signed_version(
            db,
            employee_id="employee-1",
            document_id=document.id,
            file_bytes=b"",
            original_filename="signed.pdf",
            uploaded_by_sub="admin-sub",
            signed_at=None,
            storage=storage,
        )

    assert storage.put_calls == []


def test_signed_version_stores_sha256(db):
    document = _document(db)
    storage = FakeStorage()
    pdf = _pdf_bytes()

    version = service.append_signed_version(
        db,
        employee_id="employee-1",
        document_id=document.id,
        file_bytes=pdf,
        original_filename="signed.pdf",
        uploaded_by_sub="admin-sub",
        signed_at=None,
        storage=storage,
    )

    assert version.sha256 == hashlib.sha256(pdf).hexdigest()


def test_void_document_retains_versions_and_hides_employee_current_list(db):
    document = _document(db)
    storage = FakeStorage()
    version = service.append_signed_version(
        db,
        employee_id="employee-1",
        document_id=document.id,
        file_bytes=_pdf_bytes(),
        original_filename="signed.pdf",
        uploaded_by_sub="admin-sub",
        signed_at=None,
        storage=storage,
    )

    service.void_document(
        db,
        employee_id="employee-1",
        document_id=document.id,
        reason="Documento reemplazado por novación",
        actor_sub="admin-sub",
    )

    db.refresh(document)
    assert document.status == "VOID"
    assert document.void_reason == "Documento reemplazado por novación"
    assert db.query(EmployeeDocumentVersion).filter_by(id=version.id).one()
    assert service.list_current_signed_for_employee(
        db, employee_id="employee-1"
    ) == []


def test_void_document_rejects_new_signed_version(db):
    document = _document(db)
    storage = FakeStorage()
    service.void_document(
        db,
        employee_id="employee-1",
        document_id=document.id,
        reason="Anulado",
        actor_sub="admin-sub",
    )

    with pytest.raises(service.EmployeeDocumentStateError):
        service.append_signed_version(
            db,
            employee_id="employee-1",
            document_id=document.id,
            file_bytes=_pdf_bytes(),
            original_filename="signed.pdf",
            uploaded_by_sub="admin-sub",
            signed_at=None,
            storage=storage,
        )


def test_db_failure_after_upload_cleans_new_s3_object(db, monkeypatch):
    document = _document(db)
    storage = FakeStorage()
    pdf = _pdf_bytes()

    def fail_commit():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(db, "commit", fail_commit)

    with pytest.raises(service.EmployeeDocumentStorageError):
        service.append_signed_version(
            db,
            employee_id="employee-1",
            document_id=document.id,
            file_bytes=pdf,
            original_filename="signed.pdf",
            uploaded_by_sub="admin-sub",
            signed_at=None,
            storage=storage,
        )

    assert len(storage.put_calls) == 1
    uploaded_key = storage.put_calls[0][0]
    assert storage.delete_calls == [uploaded_key]
    assert uploaded_key not in storage.objects


def test_hr_list_can_include_history_while_employee_list_only_current(db):
    document = _document(db)
    storage = FakeStorage()
    first = service.append_signed_version(
        db,
        employee_id="employee-1",
        document_id=document.id,
        file_bytes=_pdf_bytes(),
        original_filename="v1.pdf",
        uploaded_by_sub="admin-sub",
        signed_at=None,
        storage=storage,
    )
    second = service.append_signed_version(
        db,
        employee_id="employee-1",
        document_id=document.id,
        file_bytes=_pdf_bytes() + b"\n% v2",
        original_filename="v2.pdf",
        uploaded_by_sub="admin-sub",
        signed_at=None,
        storage=storage,
    )

    hr_items = service.list_documents_for_hr(db, employee_id="employee-1")
    employee_items = service.list_current_signed_for_employee(
        db, employee_id="employee-1"
    )

    assert [item.id for item in hr_items] == [document.id]
    assert [item.id for item in employee_items] == [document.id]
    payload = service.document_payload(hr_items[0], db=db, include_history=True)
    assert [item["id"] for item in payload["versions"]] == [second.id, first.id]
    assert payload["current_signed_version"]["id"] == second.id


def test_ensure_initial_contract_requires_structured_contract_sync(db):
    with pytest.raises(service.EmployeeDocumentValidationError):
        service.ensure_initial_contract_document(
            db,
            employee_id="employee-1",
            created_by_sub="admin-sub",
        )
