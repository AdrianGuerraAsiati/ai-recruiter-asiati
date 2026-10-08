"""Tests for persistent talent coverage, without invoking AI."""
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.domains.ranking.router import get_talent_coverage_summary


def test_coverage_uses_valid_country_and_job_versions():
    job1 = SimpleNamespace(id="j1", title="Analista", work_mode="ONSITE", country_code="CO")
    job2 = SimpleNamespace(id="j2", title="Ingeniero", work_mode="REMOTE", country_code=None)
    def evaluation(job, candidate, score, created=None):
        return (SimpleNamespace(job_id=job.id, candidate_id=candidate.id,
                                match_score=score, created_at=created), candidate, job)
    candidates = [SimpleNamespace(id=f"c{i}", country_code="CO") for i in range(4)]
    remote = [SimpleNamespace(id=f"r{i}", country_code="MX") for i in range(3)]
    wrong_country = SimpleNamespace(id="outside", country_code="MX")
    rows = ([evaluation(job1, candidate, 75) for candidate in candidates[:3]]
            + [evaluation(job1, wrong_country, 100)]
            + [evaluation(job2, candidate, 85) for candidate in remote])
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [job1, job2]
    db.query.return_value.join.return_value.join.return_value.filter.return_value.all.return_value = rows

    result = get_talent_coverage_summary(db=db, _user={"sub": "admin"})

    assert result["covered_jobs"] == 2
    assert result["coverage_percent"] == 100
    assert result["counts"]["strong"] == 1
    assert result["counts"]["covered"] == 2
    assert result["jobs"][0]["viable"] == 3
    assert result["jobs"][1]["strong"] == 3


def test_unranked_jobs_are_pending_not_critical():
    job = SimpleNamespace(id="j1", title="Sin evaluar", work_mode="ONSITE", country_code="CO")
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [job]
    db.query.return_value.join.return_value.join.return_value.filter.return_value.all.return_value = []

    result = get_talent_coverage_summary(db=db, _user={"sub": "admin"})

    assert result["counts"]["pending"] == 1
    assert result["counts"]["critical"] == 0
    assert result["coverage_percent"] == 0
