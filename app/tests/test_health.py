"""Tests for liveness and readiness endpoints."""

import os
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import app.db as db_mod
import app.health as health_mod
from app.main import app


@pytest.fixture(scope="function")
def client(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    if db_mod._engine is not None:
        db_mod._engine.dispose()
    db_mod._engine = None
    db_mod._SessionLocal = None
    with TestClient(app) as test_client:
        yield test_client
    if db_mod._engine is not None:
        db_mod._engine.dispose()
    db_mod._engine = None
    db_mod._SessionLocal = None


class TestHealthChecks:
    def test_liveness_does_not_require_database_configuration(self, client):
        with patch.dict(os.environ, {"DATABASE_URL": ""}):
            response = client.get("/live")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_readiness_fails_when_database_is_not_configured(self, client):
        with patch.dict(os.environ, {"DATABASE_URL": ""}):
            response = client.get("/ready")

        assert response.status_code == 503
        assert response.json() == {"status": "unhealthy", "db": False}

    def test_readiness_returns_200_when_database_responds(self, client):
        response = client.get("/ready")

        assert response.status_code == 200
        assert response.json() == {"status": "ok", "db": True}

    def test_legacy_health_alias_remains_readiness_compatible(self, client):
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json()["db"] is True

    def test_readiness_returns_503_when_database_connection_fails(
        self,
        client,
        monkeypatch,
    ):
        class BrokenEngine:
            @contextmanager
            def connect(self):
                raise RuntimeError("database unavailable")
                yield

        monkeypatch.setenv("DATABASE_URL", "postgresql://configured")
        monkeypatch.setattr(health_mod, "get_engine", lambda: BrokenEngine())

        response = client.get("/api/ready")

        assert response.status_code == 503
        assert response.json() == {"status": "unhealthy", "db": False}
