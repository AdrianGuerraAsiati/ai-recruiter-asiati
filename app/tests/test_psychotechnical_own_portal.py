from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.domains.psychotechnical import own_router

CID = "f8f50fc2-7cb4-4efe-b7bb-80c5fcb64ebd"
PRINCIPAL = {"profile": {"id": "user-profile-123"}, "sub": "applicant-sub"}


def test_own_assignments_uses_profile_link_not_email():
    db = MagicMock()
    db.query.return_value.join.return_value.filter.return_value.distinct.return_value.order_by.return_value.all.return_value = []
    result = own_router.own_assignments(db=db, principal=PRINCIPAL)
    assert result == {"items": []}
    assert db.query.called


def test_missing_profile_cannot_list():
    with pytest.raises(HTTPException) as error:
        own_router.own_assignments(db=MagicMock(), principal={"profile": {}})
    assert error.value.status_code == 403


def test_cannot_open_another_persons_test():
    db = MagicMock()
    db.query.return_value.join.return_value.filter.return_value.first.return_value = None
    with pytest.raises(HTTPException) as error:
        own_router.launch_own_assignment(CID, db=db, principal=PRINCIPAL)
    assert error.value.status_code == 404
    db.commit.assert_not_called()


def test_launch_does_not_reset_in_progress_state(monkeypatch):
    assignment = SimpleNamespace(id=CID, status="IN_PROGRESS", token_hash="old", expires_at=None)
    db = MagicMock()
    monkeypatch.setattr(own_router, "_own_assignment", lambda *args: assignment)
    monkeypatch.setattr(own_router.service, "_status_for", lambda row: row.status)
    monkeypatch.setattr(own_router.service, "_public_token", lambda: "fresh-token")
    monkeypatch.setattr(own_router.service, "_token_hash", lambda token: "new-hash")
    response = own_router.launch_own_assignment(CID, db=db, principal=PRINCIPAL)
    assert response == {"token": "fresh-token"}
    assert assignment.status == "IN_PROGRESS"
    assert assignment.token_hash == "new-hash"
    db.commit.assert_called_once()


def test_completed_assignment_cannot_be_reopened(monkeypatch):
    assignment = SimpleNamespace(status="COMPLETED")
    db = MagicMock()
    monkeypatch.setattr(own_router, "_own_assignment", lambda *args: assignment)
    monkeypatch.setattr(own_router.service, "_status_for", lambda row: row.status)
    with pytest.raises(HTTPException) as error:
        own_router.launch_own_assignment(CID, db=db, principal=PRINCIPAL)
    assert error.value.status_code == 409
    db.commit.assert_not_called()
