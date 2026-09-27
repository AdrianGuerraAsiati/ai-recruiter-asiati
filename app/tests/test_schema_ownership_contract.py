"""Contracts for production schema ownership and startup behavior."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_application_startup_does_not_create_schema_implicitly():
    bootstrap = (ROOT / "app" / "bootstrap.py").read_text(encoding="utf-8")

    assert "create_all" not in bootstrap
    assert "ensure_rbac_catalog" in bootstrap
    assert "Alembic is the only schema owner" in bootstrap
