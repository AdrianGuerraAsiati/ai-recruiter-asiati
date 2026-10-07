"""Backend tests for job deletion with delete_candidates option."""

import os
import tempfile
import uuid

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.deps import get_current_user, get_db
from app.main import app
from app.models import Candidate, Evaluation, Job, JobCandidate, Ranking, RankingItem


@pytest.fixture()
def db_session():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()
    os.close(fd)
    os.unlink(db_path)


@pytest.fixture()
def client(db_session):
    def override():
        Session = sessionmaker(bind=db_session.get_bind())
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    app.dependency_overrides[get_current_user] = lambda: {"sub": "user-a", "email": "a@test.com"}
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _uid():
    return str(uuid.uuid4())


def _seed_job(db, title="Backend Dev", owner="user-a"):
    job = Job(id=_uid(), title=title, description="Python APIs", owner_sub=owner)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _seed_candidate(db, name="Ana", owner="user-a"):
    c = Candidate(id=_uid(), name=name, owner_sub=owner)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _assign(db, job_id, candidate_id):
    jc = JobCandidate(id=_uid(), job_id=job_id, candidate_id=candidate_id)
    db.add(jc)
    db.commit()


def _create_evaluation(db, job_id, candidate_id):
    e = Evaluation(
        id=_uid(),
        candidate_id=candidate_id,
        job_id=job_id,
        status="COMPLETED",
        match_score=75.0,
        recommendation="GOOD_MATCH",
        summary="a" * 100,
        strengths=["Python"],
        gaps=["K8s"],
    )
    db.add(e)
    db.commit()


def _create_ranking(db, job_id, candidate_id):
    ranking = Ranking(id=_uid(), job_id=job_id, ranking_version=1)
    db.add(ranking)
    db.commit()
    item = RankingItem(id=_uid(), ranking_id=ranking.id, candidate_id=candidate_id, score=75.0, position=1)
    db.add(item)
    db.commit()


# ============================================================
# Tests
# ============================================================

class TestDeleteJobOnly:
    def test_preserves_candidates(self, client, db_session):
        job = _seed_job(db_session)
        cand = _seed_candidate(db_session)
        _assign(db_session, job.id, cand.id)
        job_id = job.id
        cand_id = cand.id

        resp = client.delete(f"/api/jobs/{job_id}", params={"delete_candidates": False})
        assert resp.status_code == 200
        assert resp.json()["deleted_candidates"] == 0
        assert resp.json()["delete_candidates"] is False

        db_session.expire_all()
        assert db_session.query(Candidate).filter(Candidate.id == cand_id).first() is not None

    def test_removes_job_candidate_links(self, client, db_session):
        job = _seed_job(db_session)
        cand = _seed_candidate(db_session)
        _assign(db_session, job.id, cand.id)
        job_id = job.id

        client.delete(f"/api/jobs/{job_id}", params={"delete_candidates": False})

        db_session.expire_all()
        links = db_session.query(JobCandidate).filter(JobCandidate.job_id == job_id).all()
        assert links == []

    def test_removes_evaluations(self, client, db_session):
        job = _seed_job(db_session)
        cand = _seed_candidate(db_session)
        _assign(db_session, job.id, cand.id)
        _create_evaluation(db_session, job.id, cand.id)
        job_id = job.id

        client.delete(f"/api/jobs/{job_id}", params={"delete_candidates": False})

        db_session.expire_all()
        evals = db_session.query(Evaluation).filter(Evaluation.job_id == job_id).all()
        assert evals == []

    def test_removes_ranking_and_ranking_items(self, client, db_session):
        job = _seed_job(db_session)
        cand = _seed_candidate(db_session)
        _assign(db_session, job.id, cand.id)
        _create_ranking(db_session, job.id, cand.id)
        job_id = job.id

        client.delete(f"/api/jobs/{job_id}", params={"delete_candidates": False})

        db_session.expire_all()
        rankings = db_session.query(Ranking).filter(Ranking.job_id == job_id).all()
        assert rankings == []

    def test_response_fields(self, client, db_session):
        job = _seed_job(db_session)
        job_id = job.id
        resp = client.delete(f"/api/jobs/{job_id}", params={"delete_candidates": False})
        data = resp.json()
        assert data["detail"] == "Vacante eliminada."
        assert data["job_id"] == job_id
        assert data["delete_candidates"] is False
        assert data["deleted_candidates"] == 0


class TestDeleteJobWithCandidates:
    def test_deletes_assigned_candidates(self, client, db_session):
        job = _seed_job(db_session)
        cand = _seed_candidate(db_session)
        _assign(db_session, job.id, cand.id)
        job_id = job.id
        cand_id = cand.id

        resp = client.delete(f"/api/jobs/{job_id}", params={"delete_candidates": True})
        assert resp.status_code == 200
        assert resp.json()["deleted_candidates"] == 1

        db_session.expire_all()
        assert db_session.query(Candidate).filter(Candidate.id == cand_id).first() is None

    def test_does_not_delete_unassigned_candidate(self, client, db_session):
        job = _seed_job(db_session)
        cand = _seed_candidate(db_session, name="NotAssigned")
        job_id = job.id
        cand_id = cand.id

        client.delete(f"/api/jobs/{job_id}", params={"delete_candidates": True})

        db_session.expire_all()
        assert db_session.query(Candidate).filter(Candidate.id == cand_id).first() is not None

    def test_shared_candidate_preserved_when_false(self, client, db_session):
        job_a = _seed_job(db_session, title="Job A")
        job_b = _seed_job(db_session, title="Job B")
        shared = _seed_candidate(db_session, name="Shared")
        job_a_id = job_a.id
        job_b_id = job_b.id
        shared_id = shared.id

        _assign(db_session, job_a_id, shared_id)
        _assign(db_session, job_b_id, shared_id)

        client.delete(f"/api/jobs/{job_a_id}", params={"delete_candidates": False})

        db_session.expire_all()
        assert db_session.query(Candidate).filter(Candidate.id == shared_id).first() is not None
        link_b = db_session.query(JobCandidate).filter(
            JobCandidate.job_id == job_b_id, JobCandidate.candidate_id == shared_id
        ).first()
        assert link_b is not None

    def test_shared_candidate_deleted_when_true(self, client, db_session):
        job_a = _seed_job(db_session, title="Job A")
        job_b = _seed_job(db_session, title="Job B")
        shared = _seed_candidate(db_session, name="Shared")
        job_a_id = job_a.id
        job_b_id = job_b.id
        shared_id = shared.id

        _assign(db_session, job_a_id, shared_id)
        _assign(db_session, job_b_id, shared_id)

        resp = client.delete(f"/api/jobs/{job_a_id}", params={"delete_candidates": True})
        assert resp.json()["deleted_candidates"] == 1

        db_session.expire_all()
        assert db_session.query(Candidate).filter(Candidate.id == shared_id).first() is None
        link_b = db_session.query(JobCandidate).filter(
            JobCandidate.job_id == job_b_id, JobCandidate.candidate_id == shared_id
        ).first()
        assert link_b is None
        assert db_session.query(Job).filter(Job.id == job_b_id).first() is not None

    def test_response_fields(self, client, db_session):
        job = _seed_job(db_session)
        cand = _seed_candidate(db_session)
        _assign(db_session, job.id, cand.id)
        job_id = job.id

        resp = client.delete(f"/api/jobs/{job_id}", params={"delete_candidates": True})
        data = resp.json()
        assert data["detail"] == "Vacante y candidatos eliminados."
        assert data["delete_candidates"] is True
        assert data["deleted_candidates"] == 1


class TestDeleteJobGlobalAdminAccess:
    def test_admin_can_delete_job_created_by_another_admin(self, client, db_session):
        job = _seed_job(db_session, owner="user-b")
        job_id = job.id

        resp = client.delete(f"/api/jobs/{job_id}", params={"delete_candidates": False})
        assert resp.status_code == 200
        db_session.expire_all()
        assert db_session.query(Job).filter(Job.id == job_id).first() is None

    def test_explicit_delete_candidates_ignores_creator_provenance(self, client, db_session):
        job = _seed_job(db_session, owner="user-a")
        other_cand = _seed_candidate(db_session, name="Other", owner="user-b")
        job_id = job.id
        other_id = other_cand.id

        jc = JobCandidate(id=_uid(), job_id=job_id, candidate_id=other_id)
        db_session.add(jc)
        db_session.commit()

        resp = client.delete(f"/api/jobs/{job_id}", params={"delete_candidates": True})
        assert resp.status_code == 200
        assert resp.json()["deleted_candidates"] == 1

        db_session.expire_all()
        assert db_session.query(Candidate).filter(Candidate.id == other_id).first() is None


class TestJobStatus:
    def test_admin_can_pause_and_reactivate_job(self, client, db_session):
        job = _seed_job(db_session)
        job_id = job.id

        paused = client.put(
            f"/api/jobs/{job_id}/status",
            json={"status": "PAUSED"},
        )
        assert paused.status_code == 200
        assert paused.json()["status"] == "PAUSED"

        db_session.expire_all()
        assert db_session.query(Job).filter(Job.id == job_id).one().status == "PAUSED"

        active = client.put(
            f"/api/jobs/{job_id}/status",
            json={"status": "ACTIVE"},
        )
        assert active.status_code == 200
        assert active.json()["status"] == "ACTIVE"

        db_session.expire_all()
        assert db_session.query(Job).filter(Job.id == job_id).one().status == "ACTIVE"

    def test_job_status_rejects_unknown_state(self, client, db_session):
        job = _seed_job(db_session)

        response = client.put(
            f"/api/jobs/{job.id}/status",
            json={"status": "CLOSED"},
        )

        assert response.status_code == 422


class TestJobCompanyPersistence:
    def test_create_and_update_job_persist_company_name(self, client, db_session):
        created = client.post(
            "/api/jobs",
            json={
                "title": "KAM Colombia",
                "description": "Gestión de cuentas estratégicas.",
                "country_code": "CO",
                "company_name": "ASIATI Colombia",
                "city": "Bogotá",
            },
        )
        assert created.status_code == 201
        job_id = created.json()["job_id"]

        db_session.expire_all()
        job = db_session.query(Job).filter(Job.id == job_id).one()
        assert job.company_name == "ASIATI Colombia"

        updated = client.put(
            f"/api/jobs/{job_id}",
            json={
                "title": "KAM Colombia",
                "company_name": "ASIATI Corp Colombia",
            },
        )
        assert updated.status_code == 200

        db_session.expire_all()
        job = db_session.query(Job).filter(Job.id == job_id).one()
        assert job.company_name == "ASIATI Corp Colombia"



class TestJobWorkMode:
    def test_create_and_update_persist_work_mode(self, client, db_session):
        created = client.post(
            "/api/jobs",
            json={
                "title": "Analista remoto",
                "description": "Vacante de prueba.",
                "country_code": "CO",
                "work_mode": "REMOTE",
            },
        )
        assert created.status_code == 201
        assert created.json()["work_mode"] == "REMOTE"
        job_id = created.json()["job_id"]

        updated = client.put(
            f"/api/jobs/{job_id}",
            json={"work_mode": "HYBRID"},
        )
        assert updated.status_code == 200
        assert updated.json()["work_mode"] == "HYBRID"

        db_session.expire_all()
        job = db_session.query(Job).filter(Job.id == job_id).one()
        assert job.work_mode == "HYBRID"

    def test_changing_country_or_work_mode_invalidates_saved_ranking(
        self,
        client,
        db_session,
    ):
        job = _seed_job(db_session)
        job.country_code = "CO"
        job.work_mode = "ONSITE"
        candidate = _seed_candidate(db_session)
        ranking = Ranking(
            id=_uid(),
            job_id=job.id,
            ranking_version=1,
            mode="full",
            notes="scope:all",
        )
        db_session.add(ranking)
        db_session.flush()
        db_session.add(
            RankingItem(
                id=_uid(),
                ranking_id=ranking.id,
                candidate_id=candidate.id,
                score=80,
                position=1,
            )
        )
        db_session.commit()

        response = client.put(
            f"/api/jobs/{job.id}",
            json={"work_mode": "REMOTE"},
        )
        assert response.status_code == 200

        db_session.expire_all()
        assert db_session.query(Ranking).filter(Ranking.job_id == job.id).count() == 0
        assert db_session.query(RankingItem).count() == 0


class TestJobsPageStatusFilter:
    def test_filters_active_and_paused_vacancies(self, client, db_session):
        active = Job(
            id=_uid(),
            title="Vacante activa",
            description="Activa",
            owner_sub="user-a",
            status="ACTIVE",
        )
        paused = Job(
            id=_uid(),
            title="Vacante pausada",
            description="Pausada",
            owner_sub="user-a",
            status="PAUSED",
        )
        db_session.add_all([active, paused])
        db_session.commit()

        active_response = client.get("/api/jobs/page", params={"status": "ACTIVE"})
        assert active_response.status_code == 200
        active_payload = active_response.json()
        assert active_payload["total"] == 1
        assert [item["title"] for item in active_payload["items"]] == ["Vacante activa"]

        paused_response = client.get("/api/jobs/page", params={"status": "PAUSED"})
        assert paused_response.status_code == 200
        paused_payload = paused_response.json()
        assert paused_payload["total"] == 1
        assert [item["title"] for item in paused_payload["items"]] == ["Vacante pausada"]

    def test_rejects_unknown_vacancy_status_filter(self, client):
        response = client.get("/api/jobs/page", params={"status": "CLOSED"})
        assert response.status_code == 422
