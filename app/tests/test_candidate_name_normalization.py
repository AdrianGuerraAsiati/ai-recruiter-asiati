"""Regression checks for the guarded candidate-name normalization workflow."""
from app.domains.candidates.name_normalization_router import (
    ApplyRequest,
    NameApproval,
    _flag,
    _valid_name,
)


def test_suspicious_import_artifacts_are_flagged():
    assert _flag("Computrabajo profile") == "suspected_import_artifact"
    assert _flag("Oferta Director financiero - Latam") == "suspected_import_artifact"
    assert _flag("No tengo empleo") == "suspected_import_artifact"
    assert _flag("María González") is None


def test_name_rejects_hallucinations_without_exact_evidence():
    assert _valid_name("María González", "Nombre completo: María González")
    assert not _valid_name("María González", "Experiencia de cinco años")
    assert not _valid_name("Oferta Director financiero", "Oferta Director financiero")
    assert not _valid_name("M", "M")


def test_approval_contract_requires_bounded_explicit_cohort():
    approval = NameApproval(
        candidate_id="f8f50fc2-7cb4-4efe-b7bb-80c5fcb64ebd",
        expected_current_name="Computrabajo",
        proposed_name="María González",
    )
    assert ApplyRequest(approvals=[approval]).approvals[0] == approval
