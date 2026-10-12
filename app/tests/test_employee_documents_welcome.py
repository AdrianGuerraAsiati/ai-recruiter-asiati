"""Unit tests for hiring welcome emails and document review inbox."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.domains.employee_documents import notifications, service
from app.domains.employee_documents.models import EmployeeDocument, EmployeeDocumentEmail
from app.models import UserProfile


class FakeSES:
    def __init__(self, *, fail=False):
        self.calls = []
        self.fail = fail

    def send_email(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("Delivery unavailable")
        return {"MessageId": "test-only"}


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def new_employee(db):
    profile = UserProfile(
        email="candidate@example.com",
        first_name="Lucia",
        last_name="Test",
        login_username="lucia.test",
        status="ACTIVE",
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def test_welcome_checklist_excludes_approved_items(db):
    employee = new_employee(db)
    db.add(EmployeeDocument(
        employee_id=employee.id,
        document_type="RESUME",
        review_status="APPROVED",
    ))
    db.commit()
    subject, body = notifications.welcome_message(db, employee)
    assert "Felicitaciones" in subject
    assert "Lucia" in body
    assert "Documento de identidad" in body
    assert "Hoja de vida actualizada" not in body
    assert "https://talent.asiaticorp.com/documents" in body
    assert "lucia.test" in body


def test_welcome_is_sent_once(db, monkeypatch):
    employee = new_employee(db)
    monkeypatch.setenv("TALENT_ID_FROM_EMAIL", "verified@example.com")
    ses = FakeSES()
    first = notifications.send_welcome(db, employee.id, ses_client=ses)
    again = notifications.send_welcome(db, employee.id, ses_client=ses)
    assert first["status"] == "SENT"
    assert again["status"] == "SENT"
    assert len(ses.calls) == 1
    assert db.query(EmployeeDocumentEmail).count() == 1


def test_delivery_error_is_recorded_and_retryable(db, monkeypatch):
    employee = new_employee(db)
    monkeypatch.setenv("TALENT_ID_FROM_EMAIL", "verified@example.com")
    failure = notifications.send_welcome(db, employee.id, ses_client=FakeSES(fail=True))
    assert failure["status"] == "FAILED"
    assert notifications.send_welcome(db, employee.id, ses_client=FakeSES())["status"] == "SENT"


def test_review_queue_shows_only_documents_awaiting_attention(db):
    employee = new_employee(db)
    db.add(EmployeeDocument(
        employee_id=employee.id,
        document_type="RESUME",
        review_status="PENDING_REVIEW",
    ))
    db.commit()
    result = service.review_queue(db)
    assert result["items"][0]["profile_id"] == employee.id
    assert result["items"][0]["pending_review"] == 1
