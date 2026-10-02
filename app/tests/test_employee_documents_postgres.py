"""PostgreSQL concurrency coverage for employee signed document versions."""

import os
import threading
import uuid

import fitz
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.domains.employee_documents import service
from app.domains.employee_documents.storage import EmployeeDocumentStorageConfig
from app.models import EmployeeDocument, UserProfile


class SharedStorage:
    def __init__(self):
        self.config = EmployeeDocumentStorageConfig(bucket="test")
        self.objects = {}
        self.lock = threading.Lock()

    def put_bytes(self, key, body, content_type):
        with self.lock:
            self.objects[key] = bytes(body)

    def delete_object(self, key):
        with self.lock:
            self.objects.pop(key, None)


def _pdf_bytes(marker):
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), marker)
    data = document.tobytes()
    document.close()
    return data


def test_concurrent_signed_uploads_allocate_distinct_versions():
    url = os.getenv("DATABASE_URL", "")
    if not url.startswith(("postgresql://", "postgresql+")):
        pytest.skip("PostgreSQL concurrency test only")

    engine = create_engine(url)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    storage = SharedStorage()
    suffix = uuid.uuid4().hex
    employee_id = f"employee-concurrency-{suffix}"

    setup = Session()
    employee = UserProfile(
        id=employee_id,
        cognito_sub=f"sub-{suffix}",
        email=f"{suffix}@example.com",
        status="ACTIVE",
    )
    document = EmployeeDocument(
        employee_id=employee_id,
        document_type="CONTRACT",
        title="Contrato laboral",
        status="DRAFT",
        created_by_sub="admin-sub",
    )
    setup.add(employee)
    setup.commit()
    setup.add(document)
    setup.commit()
    document_id = document.id
    setup.close()

    barrier = threading.Barrier(2)
    version_ids = []
    errors = []

    def upload(marker):
        session = Session()
        try:
            barrier.wait()
            version = service.append_signed_version(
                session,
                employee_id=employee_id,
                document_id=document_id,
                file_bytes=_pdf_bytes(marker),
                original_filename=f"{marker}.pdf",
                uploaded_by_sub="admin-sub",
                signed_at=None,
                storage=storage,
            )
            version_ids.append(version.id)
        except Exception as exc:  # pragma: no cover - asserted below
            errors.append(exc)
        finally:
            session.close()

    threads = [
        threading.Thread(target=upload, args=("one",)),
        threading.Thread(target=upload, args=("two",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert errors == []
    verify = Session()
    try:
        current = verify.query(EmployeeDocument).filter_by(id=document_id).one()
        versions = (
            verify.query(service.EmployeeDocumentVersion)
            .filter_by(document_id=document_id)
            .order_by(service.EmployeeDocumentVersion.version_number)
            .all()
        )
        assert [version.version_number for version in versions] == [1, 2]
        assert current.current_signed_version_id in version_ids
        assert sum(
            version.id == current.current_signed_version_id for version in versions
        ) == 1
    finally:
        verify.close()
        engine.dispose()
