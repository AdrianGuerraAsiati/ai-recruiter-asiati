"""Safety coverage for the one-shot vacancy purge."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Candidate, Job, JobCandidate
from app.scripts.purge_jobs_keep_candidates import purge_jobs_keep_candidates


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return engine, Session()


def test_purge_deletes_all_jobs_but_preserves_candidate_records():
    engine, db = _session()
    try:
        candidate = Candidate(
            name="Candidata conservada",
            email="candidate@example.com",
            owner_sub="admin-sub",
        )
        first_job = Job(
            title="Vacante uno",
            description="Uno",
            owner_sub="admin-sub",
        )
        second_job = Job(
            title="Vacante dos",
            description="Dos",
            owner_sub="admin-sub",
        )
        db.add_all([candidate, first_job, second_job])
        db.flush()
        db.add_all([
            JobCandidate(job_id=first_job.id, candidate_id=candidate.id),
            JobCandidate(job_id=second_job.id, candidate_id=candidate.id),
        ])
        db.commit()

        result = purge_jobs_keep_candidates(db, synchronize_odoo=False)

        assert result["status"] == "OK"
        assert result["jobs_before"] == 2
        assert result["jobs_deleted"] == 2
        assert result["jobs_after"] == 0
        assert result["candidates_before"] == 1
        assert result["candidates_after"] == 1
        assert result["candidates_preserved"] is True
        assert db.query(Job).count() == 0
        assert db.query(JobCandidate).count() == 0
        assert db.query(Candidate).count() == 1
        assert db.query(Candidate).one().email == "candidate@example.com"
    finally:
        db.close()
        engine.dispose()
