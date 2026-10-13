from types import SimpleNamespace
from unittest.mock import MagicMock

from app.domains.ranking.prematch_store import refresh_candidate_suggestions


def candidate():
    return SimpleNamespace(id="candidate-1", is_banned=False, country_code="CO",
                           metadata_={"cv_profile": {"skills": ["Python", "AWS"]}})


def job(status="ACTIVE", version=1):
    return SimpleNamespace(id="job-1", status=status, work_mode="REMOTE",
                           country_code="CO", evaluation_version=version,
                           evaluation_profile={"required_technologies": ["Python", "AWS"]})


def test_refresh_is_idempotent_and_keeps_applications_untouched():
    db = MagicMock()
    person = candidate()
    first = refresh_candidate_suggestions(db, person, [job()])
    assert first["computed"] == 1
    assert first["suggested"] == 1
    second = refresh_candidate_suggestions(db, person, [job()])
    assert second["computed"] == 0
    assert second["reused"] == 1
    assert db.commit.call_count == 2
    assert db.add.call_count == 0
    assert "job-1" in person.metadata_["prematch_v1"]["items"]


def test_vacancy_version_invalidates_cached_result():
    db = MagicMock()
    person = candidate()
    refresh_candidate_suggestions(db, person, [job()])
    changed = refresh_candidate_suggestions(db, person, [job(version=2)])
    assert changed["computed"] == 1


def test_pausing_job_prunes_suggestion():
    db = MagicMock()
    person = candidate()
    refresh_candidate_suggestions(db, person, [job()])
    refresh_candidate_suggestions(db, person, [job(status="PAUSED")])
    assert person.metadata_["prematch_v1"]["items"] == {}


def test_missing_cv_profile_not_treated_as_rejection():
    db = MagicMock()
    person = candidate()
    person.metadata_ = {}
    result = refresh_candidate_suggestions(db, person, [job()])
    assert result["needs_review"] == 1
    assert result["suggested"] == 0
