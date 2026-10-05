"""Tests for job-specific weighted candidate scoring."""

from app.domains.evaluations.scoring import (
    calculate_weighted_match_score,
    mandatory_gaps,
    normalize_requirement_profiles,
)


def test_job_specific_importance_changes_score():
    profiles = normalize_requirement_profiles(
        [
            {
                "requirement": "Pregrado profesional",
                "category": "EDUCATION",
                "importance": "CRITICAL",
                "mandatory": True,
            },
            {
                "requirement": "Excel intermedio",
                "category": "TECHNICAL_SKILL",
                "importance": "LOW",
                "mandatory": False,
            },
        ]
    )

    score_with_degree = calculate_weighted_match_score(
        [
            {**profiles[0], "status": "MATCH"},
            {**profiles[1], "status": "MISSING"},
        ]
    )
    score_with_only_excel = calculate_weighted_match_score(
        [
            {**profiles[0], "status": "MISSING"},
            {**profiles[1], "status": "MATCH"},
        ]
    )

    assert score_with_degree == 83
    assert score_with_only_excel == 17


def test_operational_role_does_not_invent_degree_requirement():
    profiles = normalize_requirement_profiles(
        [
            {
                "requirement": "Licencia de conducción A2 vigente",
                "category": "CERTIFICATION_LICENSE",
                "importance": "CRITICAL",
                "mandatory": True,
            },
            {
                "requirement": "Conocimiento de nomenclatura urbana",
                "category": "EXPERIENCE",
                "importance": "HIGH",
                "mandatory": False,
            },
        ]
    )

    names = [item["requirement"].casefold() for item in profiles]
    assert all("pregrado" not in name for name in names)
    assert all("profesional" not in name for name in names)


def test_legacy_string_requirements_keep_equal_weighting():
    profiles = normalize_requirement_profiles(["Python", "AWS"])

    assert [item["weight"] for item in profiles] == [1.0, 1.0]
    assert calculate_weighted_match_score(
        [
            {**profiles[0], "status": "MATCH"},
            {**profiles[1], "status": "MISSING"},
        ]
    ) == 50


def test_mandatory_gap_is_reported_separately():
    requirements = [
        {
            "requirement": "Licencia de conducción",
            "mandatory": True,
            "status": "MISSING",
        },
        {
            "requirement": "Excel",
            "mandatory": False,
            "status": "MISSING",
        },
    ]

    assert mandatory_gaps(requirements) == ["Licencia de conducción"]


class _PromptStub:
    def __init__(self, name):
        self.name = name

    def __or__(self, _other):
        return self.name


def test_evaluator_uses_structured_weighted_requirements(monkeypatch):
    import app.infrastructure.bedrock.evaluator as evaluator_module

    monkeypatch.setattr(
        evaluator_module,
        "REQUIREMENT_EXTRACTION_PROMPT",
        _PromptStub("extract"),
    )
    monkeypatch.setattr(
        evaluator_module,
        "CANDIDATE_EVALUATION_PROMPT",
        _PromptStub("evaluate"),
    )
    monkeypatch.setattr(evaluator_module, "get_llm", lambda: object())

    def fake_invoke(chain, payload, description):
        if chain == "extract":
            return {
                "requirements": [
                    {
                        "requirement": "Pregrado profesional",
                        "category": "EDUCATION",
                        "importance": "CRITICAL",
                        "mandatory": True,
                    },
                    {
                        "requirement": "Excel intermedio",
                        "category": "TECHNICAL_SKILL",
                        "importance": "LOW",
                        "mandatory": False,
                    },
                ]
            }
        assert chain == "evaluate"
        return {
            "requirements": [
                {
                    "requirement": "Pregrado profesional",
                    "status": "MATCH",
                    "evidence": "Profesional en Administración de Empresas.",
                },
                {
                    "requirement": "Excel intermedio",
                    "status": "MISSING",
                    "evidence": None,
                },
            ]
        }

    monkeypatch.setattr(evaluator_module, "invoke_json_prompt", fake_invoke)

    result = evaluator_module.evaluate_candidate(
        candidate_id="cand-1",
        job_description="Pregrado requerido. Excel deseable.",
        results=[
            {
                "content": {
                    "text": (
                        "Profesional en Administración de Empresas. "
                        "Experiencia en operaciones y servicio al cliente."
                    )
                }
            }
        ],
    )

    assert result["match_score"] == 83
    assert result["recommendation"] == "STRONG_MATCH"
    assert result["scoring_version"] == "weighted_requirements_v2"
    assert result["mandatory_gaps"] == []
    assert result["requirements"][0]["weight"] == 5.0
    assert result["requirements"][1]["weight"] == 1.0
    assert result["requirements"][0]["category"] == "EDUCATION"
