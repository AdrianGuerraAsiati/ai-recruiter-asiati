"""Model registration coverage for employee documents."""

from app.db import Base
import app.models  # noqa: F401


def test_employee_document_models_register_expected_tables():
    assert "employee_documents" in Base.metadata.tables
    assert "employee_document_artifacts" in Base.metadata.tables
    assert "employee_document_versions" in Base.metadata.tables
