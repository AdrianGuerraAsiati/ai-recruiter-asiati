"""Observability contracts for HTTP and background work."""

import json
import logging
import os

from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app.bootstrap import create_app
from app.observability import JsonFormatter, correlation_scope
from app.infrastructure.imports.queue import ReceivedImportMessage
from app.workers import candidate_imports


def test_http_request_id_is_preserved_and_returned():
    app = create_app()

    with TestClient(app) as client:
        response = client.get("/live", headers={"X-Request-ID": "test-request-123"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "test-request-123"


def test_invalid_http_request_id_is_replaced():
    app = create_app()

    with TestClient(app) as client:
        response = client.get("/live", headers={"X-Request-ID": "not valid with spaces"})

    request_id = response.headers["X-Request-ID"]
    assert request_id
    assert request_id != "not valid with spaces"
    assert len(request_id) == 32


def test_json_formatter_emits_active_correlation_id():
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test.observability",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )

    with correlation_scope("batch:abc"):
        payload = json.loads(formatter.format(record))

    assert payload["message"] == "hello"
    assert payload["correlation_id"] == "batch:abc"
    assert payload["level"] == "INFO"


def test_worker_logs_and_acks_with_batch_correlation(monkeypatch, caplog):
    monkeypatch.setattr(candidate_imports, "process_batch", lambda *args, **kwargs: None)
    deleted = []
    monkeypatch.setattr(candidate_imports.queue, "delete_message", deleted.append)

    message = ReceivedImportMessage(
        batch_id="batch-123",
        receipt_handle="receipt-1",
        receive_count=1,
    )

    with caplog.at_level(logging.INFO):
        candidate_imports.handle_message(message)

    assert deleted == ["receipt-1"]
    completed = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "candidate_import_completed"
    ]
    assert len(completed) == 1
    assert completed[0].batch_id == "batch-123"
