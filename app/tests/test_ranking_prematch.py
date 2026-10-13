"""Pre-matching must never confuse absent evidence with a failed candidate."""
from types import SimpleNamespace

from app.domains.ranking.prematch import compare_candidate_job


def candidate(**kwargs):
    return SimpleNamespace(**{**{"is_banned": False, "country_code": "CO",
                           "metadata_": {"cv_profile": {"skills": ["Python", "AWS", "PostgreSQL"]}}}, **kwargs})


def vacancy(**kwargs):
    return SimpleNamespace(**{**{"status": "ACTIVE", "work_mode": "ONSITE",
                           "country_code": "CO",
                           "evaluation_profile": {"required_technologies": ["Python", "AWS"]}}, **kwargs})


def test_pre_match_above_threshold():
    result = compare_candidate_job(candidate(), vacancy())
    assert result["status"] == "SUGGESTED"
    assert result["score"] == 100
    assert result["version"] == "rules-v1"


def test_pre_match_does_not_create_application_or_invoke_llm():
    result = compare_candidate_job(candidate(), vacancy(evaluation_profile={"required_technologies": ["Python", "Java"]}))
    assert result["score"] == 50
    assert result["status"] == "SUGGESTED"
    assert len(result["matched"]) == 1


def test_missing_extracted_profile_is_unknown_not_zero():
    result = compare_candidate_job(candidate(metadata_={}), vacancy())
    assert result == {"status": "NEEDS_REVIEW", "reason": "CV_PROFILE_MISSING"}


def test_country_unknown_requires_review():
    result = compare_candidate_job(candidate(country_code=None), vacancy())
    assert result["reason"] == "COUNTRY_UNKNOWN"


def test_wrong_country_disqualified_for_onsite_only():
    result = compare_candidate_job(candidate(country_code="MX"), vacancy())
    assert result["reason"] == "COUNTRY_MISMATCH"


def test_remote_considers_other_countries():
    result = compare_candidate_job(candidate(country_code="MX"), vacancy(work_mode="REMOTE"))
    assert result["status"] == "SUGGESTED"


def test_inactive_job_is_excluded():
    result = compare_candidate_job(candidate(), vacancy(status="PAUSED"))
    assert result["reason"] == "JOB_INACTIVE"


def test_no_approved_vacancy_requirements_is_unknown():
    result = compare_candidate_job(candidate(), vacancy(evaluation_profile={}))
    assert result["reason"] == "JOB_CRITERIA_MISSING"
