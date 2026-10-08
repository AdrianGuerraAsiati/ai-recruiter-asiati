"""Focused contracts for the Evaluations HTTP application boundary."""

from types import SimpleNamespace

import pytest

from app.domains.evaluations import service


def test_global_entrypoint_resolves_objects_then_delegates(monkeypatch):
    candidate = SimpleNamespace(id="candidate-1", is_banned=False)
    job = SimpleNamespace(
        id="job-1",
        description="Python y APIs REST.",
        evaluation_profile={},
    )
    db = object()
    events = []
    expected = (SimpleNamespace(id="evaluation-1"), True, None)

    def require_candidate(db_arg, candidate_id, owner_sub):
        events.append(("candidate", db_arg, candidate_id, owner_sub))
        return candidate

    def get_job(db_arg, job_id, owner_sub=None):
        events.append(("job", db_arg, job_id, owner_sub))
        return job

    def evaluate(db_arg, *, candidate, job):
        events.append(("evaluate", db_arg, candidate.id, job.id))
        return expected

    monkeypatch.setattr(service.candidates_service, "require_candidate", require_candidate)
    monkeypatch.setattr(service.jobs_repository, "get_job", get_job)
    monkeypatch.setattr(service, "evaluate_candidate_for_job", evaluate)

    result = service.evaluate_candidate_for_owner(
        db,
        candidate_id="candidate-1",
        job_id="job-1",
        owner_sub="owner-1",
    )

    assert result is expected
    assert events == [
        ("candidate", db, "candidate-1", "owner-1"),
        ("job", db, "job-1", None),
        ("evaluate", db, "candidate-1", "job-1"),
    ]


def test_global_entrypoint_propagates_candidate_not_found(monkeypatch):
    def missing_candidate(*args, **kwargs):
        raise service.CandidateNotFound("candidate-1")

    monkeypatch.setattr(
        service.candidates_service,
        "require_candidate",
        missing_candidate,
    )

    with pytest.raises(service.CandidateNotFound):
        service.evaluate_candidate_for_owner(
            object(),
            candidate_id="candidate-1",
            job_id="job-1",
            owner_sub="owner-1",
        )


def test_global_entrypoint_raises_job_not_found(monkeypatch):
    candidate = SimpleNamespace(id="candidate-1", is_banned=False)
    monkeypatch.setattr(
        service.candidates_service,
        "require_candidate",
        lambda *args, **kwargs: candidate,
    )
    monkeypatch.setattr(
        service.jobs_repository,
        "get_job",
        lambda *args, **kwargs: None,
    )

    with pytest.raises(service.JobNotFound):
        service.evaluate_candidate_for_owner(
            object(),
            candidate_id="candidate-1",
            job_id="missing-job",
            owner_sub="owner-1",
        )



def test_global_entrypoint_rejects_banned_candidate(monkeypatch):
    candidate = SimpleNamespace(id="candidate-1", is_banned=True)
    monkeypatch.setattr(
        service.candidates_service,
        "require_candidate",
        lambda *args, **kwargs: candidate,
    )

    with pytest.raises(service.CandidateBanned):
        service.evaluate_candidate_for_owner(
            object(),
            candidate_id="candidate-1",
            job_id="job-1",
            owner_sub="owner-1",
        )

def _completed_llm_result():
    return {
        "match_score": 88,
        "recommendation": "STRONG_MATCH",
        "summary": (
            "La persona candidata presenta evidencia técnica sólida y suficiente "
            "para los requisitos principales de esta vacante y puede avanzar."
        ),
        "strengths": ["AWS", "Python"],
        "gaps": ["Kubernetes"],
        "requirements": [
            {
                "requirement": "AWS",
                "status": "MATCH",
                "evidence": "Experiencia comprobada.",
            }
        ],
    }


def test_candidate_evidence_returns_normalized_completed_result(monkeypatch):
    from app import evaluation as evaluation_backend

    retrieved = [{"text": "evidence"}]
    monkeypatch.setattr(
        evaluation_backend,
        "retrieve_candidate",
        lambda **kwargs: retrieved,
    )
    monkeypatch.setattr(
        evaluation_backend,
        "evaluate_candidate",
        lambda **kwargs: _completed_llm_result(),
    )

    result, internal_error = service.evaluate_candidate_evidence(
        candidate_id="candidate-1",
        evaluation_text="Cloud Engineer",
    )

    assert internal_error is None
    assert result["status"] == "COMPLETED"
    assert result["match_score"] == 88
    assert result["recommendation"] == "STRONG_MATCH"
    assert result["requirements"][0]["status"] == "MATCH"


def test_candidate_evidence_preserves_public_failed_result(monkeypatch):
    from app import evaluation as evaluation_backend

    monkeypatch.setattr(
        evaluation_backend,
        "retrieve_candidate",
        lambda **kwargs: [],
    )
    monkeypatch.setattr(
        evaluation_backend,
        "evaluate_candidate",
        lambda **kwargs: {
            "status": "FAILED",
            "recommendation": "EVALUATION_FAILED",
            "summary": "Proveedor no disponible.",
            "error_message": "MODEL_TIMEOUT",
        },
    )

    result, internal_error = service.evaluate_candidate_evidence(
        candidate_id="candidate-2",
        evaluation_text="Operations",
    )

    assert internal_error is None
    assert result["status"] == "FAILED"
    assert result["error_message"] == "MODEL_TIMEOUT"
    assert result["strengths"] == []
    assert result["gaps"] == []


def test_candidate_evidence_converts_internal_exception_to_safe_failure(monkeypatch):
    from app import evaluation as evaluation_backend

    def fail_retrieval(**kwargs):
        raise RuntimeError("provider detail")

    monkeypatch.setattr(
        evaluation_backend,
        "retrieve_candidate",
        fail_retrieval,
    )

    result, internal_error = service.evaluate_candidate_evidence(
        candidate_id="candidate-3",
        evaluation_text="Finance",
    )

    assert internal_error == "provider detail"
    assert result["status"] == "FAILED"
    assert result["recommendation"] == "EVALUATION_FAILED"
    assert result["error_message"] == service.INTERNAL_EVALUATION_ERROR_CODE
    assert result["summary"] == service.FAILED_EVALUATION_PUBLIC_MESSAGE


def test_persist_candidate_evaluation_delegates_normalized_payload(monkeypatch):
    captured = {}
    expected = SimpleNamespace(id="evaluation-1")

    def create_evaluation(db, **kwargs):
        captured.update(kwargs)
        return expected

    monkeypatch.setattr(
        service.evaluations_repository,
        "create_evaluation",
        create_evaluation,
    )
    payload = {
        "match_score": 75,
        "recommendation": "GOOD_MATCH",
        "summary": "Resumen suficientemente detallado para persistencia.",
        "strengths": ["Python"],
        "gaps": ["Terraform"],
        "requirements": [],
        "status": "COMPLETED",
        "error_message": None,
    }

    result = service.persist_candidate_evaluation(
        object(),
        candidate_id="candidate-4",
        job_id="job-4",
        job_evaluation_version=7,
        result=payload,
    )

    assert result is expected
    assert captured["candidate_id"] == "candidate-4"
    assert captured["job_id"] == "job-4"
    assert captured["job_evaluation_version"] == 7
    assert captured["match_score"] == 75
    assert captured["status"] == "COMPLETED"

