"""Contracts for durable asynchronous job reevaluation work."""

from concurrent.futures import Future

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db import Base
from app.models import Candidate, Evaluation, Job, JobCandidate, JobReevaluationTask
from app.workers import job_reevaluations


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine, Session(engine)


def _seed_job_with_candidates(db: Session, *, version: int = 2):
    job = Job(
        title="Cloud Engineer",
        description="AWS platform engineering",
        owner_sub="owner-1",
        evaluation_version=version,
    )
    current = Candidate(name="Current Candidate", owner_sub="owner-1")
    stale = Candidate(name="Stale Candidate", owner_sub="owner-1")
    outsider = Candidate(name="Other Tenant", owner_sub="owner-2")
    db.add_all([job, current, stale, outsider])
    db.flush()
    db.add_all(
        [
            JobCandidate(job_id=job.id, candidate_id=current.id),
            JobCandidate(job_id=job.id, candidate_id=stale.id),
            JobCandidate(job_id=job.id, candidate_id=outsider.id),
            Evaluation(
                candidate_id=current.id,
                job_id=job.id,
                job_evaluation_version=version,
                status="COMPLETED",
                match_score=90,
                recommendation="STRONG_MATCH",
                summary=(
                    "Current complete evaluation summary with enough detail to satisfy the "
                    "public completeness contract and prove that a current vacancy version "
                    "is reused without another model invocation."
                ),
                strengths=["AWS"],
                gaps=[],
            ),
            Evaluation(
                candidate_id=stale.id,
                job_id=job.id,
                job_evaluation_version=version - 1,
                status="COMPLETED",
                match_score=70,
                recommendation="GOOD_MATCH",
                summary=(
                    "Stale evaluation summary with enough detail to satisfy completeness "
                    "while still requiring replacement because it belongs to an older "
                    "vacancy evaluation version."
                ),
                strengths=["Python"],
                gaps=[],
            ),
        ]
    )
    task = JobReevaluationTask(
        owner_sub="owner-1",
        job_id=job.id,
        target_evaluation_version=version,
        status="PENDING",
    )
    db.add(task)
    db.commit()
    return job, current, stale, outsider, task


def test_worker_evaluates_only_stale_owned_candidates_and_materializes_once(monkeypatch):
    engine, db = _db()
    try:
        job, current, stale, outsider, task = _seed_job_with_candidates(db)
        expected_job_id = job.id
        stale_id = stale.id
        outsider_id = outsider.id
        task_id = task.id
        evaluated = []
        ranked = []

        def fake_evaluate(*, candidate_id, job_id, owner_sub, force_evaluation):
            evaluated.append(candidate_id)
            assert job_id == expected_job_id
            assert owner_sub == "owner-1"
            assert force_evaluation is False
            return True

        monkeypatch.setattr(
            job_reevaluations,
            "_evaluate_candidate_in_isolated_session",
            fake_evaluate,
        )
        monkeypatch.setattr(
            job_reevaluations.ranking_service,
            "materialize_ranking_from_evaluations",
            lambda _db, **kwargs: ranked.append(kwargs) or {"ranking_version": 3},
        )

        outcome = job_reevaluations.process_job_reevaluation(db, task_id=task_id)

        assert outcome == "COMPLETED"
        assert evaluated == [stale_id]
        assert outsider_id not in evaluated
        assert ranked == [{"job_id": expected_job_id, "owner_sub": "owner-1", "scope": "assigned"}]
        db.refresh(task)
        assert task.status == "COMPLETED"
        assert task.completed_at is not None
    finally:
        db.close()
        engine.dispose()


def test_manual_async_ranking_uses_all_scope_and_force_flag(monkeypatch):
    engine, db = _db()
    try:
        job = Job(
            title="Remote Engineer",
            description="Cloud engineering",
            owner_sub="owner-1",
            evaluation_version=1,
            work_mode="REMOTE",
        )
        first = Candidate(name="Candidate One", owner_sub="owner-1")
        second = Candidate(name="Candidate Two", owner_sub="owner-1")
        db.add_all([job, first, second])
        db.flush()
        task = JobReevaluationTask(
            owner_sub="owner-1",
            job_id=job.id,
            target_evaluation_version=1,
            scope="all",
            force_evaluation=True,
            status="PENDING",
        )
        db.add(task)
        db.commit()
        expected_job_id = job.id
        first_id = first.id
        second_id = second.id
        task_id = task.id

        evaluated = []
        ranked = []
        monkeypatch.setattr(
            job_reevaluations.ranking_service,
            "resolve_ranking_candidates",
            lambda _db, *, job, scope: [first, second],
        )

        def fake_evaluate(*, candidate_id, job_id, owner_sub, force_evaluation):
            assert job_id == expected_job_id
            assert owner_sub == "owner-1"
            evaluated.append((candidate_id, force_evaluation))
            return True

        monkeypatch.setattr(
            job_reevaluations,
            "_evaluate_candidate_in_isolated_session",
            fake_evaluate,
        )
        monkeypatch.setattr(
            job_reevaluations.ranking_service,
            "materialize_ranking_from_evaluations",
            lambda _db, **kwargs: ranked.append(kwargs) or {"ranking_version": 1},
        )

        assert job_reevaluations.process_job_reevaluation(db, task_id=task_id) == "COMPLETED"
        assert sorted(evaluated) == sorted([(first_id, True), (second_id, True)])
        assert ranked == [{"job_id": expected_job_id, "owner_sub": "owner-1", "scope": "all"}]
    finally:
        db.close()
        engine.dispose()


def test_worker_retry_does_not_duplicate_current_evaluations(monkeypatch):
    engine, db = _db()
    try:
        job, _current, stale, _outsider, task = _seed_job_with_candidates(db)
        expected_job_id = job.id
        expected_job_version = job.evaluation_version
        stale_id = stale.id
        task_id = task.id
        calls = []

        def fake_evaluate(*, candidate_id, job_id, owner_sub, force_evaluation):
            assert job_id == expected_job_id
            assert owner_sub == "owner-1"
            assert force_evaluation is False
            calls.append(candidate_id)
            return True

        monkeypatch.setattr(
            job_reevaluations,
            "_evaluate_candidate_in_isolated_session",
            fake_evaluate,
        )
        monkeypatch.setattr(
            job_reevaluations.ranking_service,
            "materialize_ranking_from_evaluations",
            lambda *_args, **_kwargs: {"ranking_version": 1},
        )

        assert job_reevaluations.process_job_reevaluation(db, task_id=task_id) == "COMPLETED"
        stale_evaluation = (
            db.query(Evaluation)
            .filter(Evaluation.job_id == expected_job_id, Evaluation.candidate_id == stale_id)
            .one()
        )
        stale_evaluation.job_evaluation_version = expected_job_version
        db.commit()
        task.status = "PENDING"
        task.completed_at = None
        db.commit()
        assert job_reevaluations.process_job_reevaluation(db, task_id=task_id) == "COMPLETED"
        assert calls == [stale_id]
    finally:
        db.close()
        engine.dispose()


def test_older_task_cannot_overwrite_newer_job_version(monkeypatch):
    engine, db = _db()
    try:
        job, _current, _stale, _outsider, task = _seed_job_with_candidates(db, version=3)
        task.target_evaluation_version = 2
        db.commit()
        calls = []
        monkeypatch.setattr(
            job_reevaluations,
            "_evaluate_candidate_in_isolated_session",
            lambda **kwargs: calls.append(kwargs),
        )
        monkeypatch.setattr(
            job_reevaluations.ranking_service,
            "materialize_ranking_from_evaluations",
            lambda *_args, **_kwargs: {"ranking_version": 1},
        )

        outcome = job_reevaluations.process_job_reevaluation(db, task_id=task.id)

        assert outcome == "SUPERSEDED"
        assert calls == []
        db.refresh(task)
        assert task.status == "COMPLETED"
        assert task.last_error_code == "SUPERSEDED_BY_NEWER_JOB_VERSION"
    finally:
        db.close()
        engine.dispose()


def test_missing_or_wrong_owner_job_fails_safely(monkeypatch):
    engine, db = _db()
    try:
        job = Job(title="Cloud Engineer", owner_sub="owner-2", evaluation_version=2)
        db.add(job)
        db.flush()
        task = JobReevaluationTask(
            owner_sub="owner-1",
            job_id=job.id,
            target_evaluation_version=2,
            status="PENDING",
        )
        db.add(task)
        db.commit()
        monkeypatch.setattr(
            job_reevaluations.ranking_service,
            "materialize_ranking_from_evaluations",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("ranking must not run")),
        )

        assert job_reevaluations.process_job_reevaluation(db, task_id=task.id) == "FAILED"
        db.refresh(task)
        assert task.status == "FAILED"
        assert task.last_error_code == "JOB_CONTEXT_MISSING"
    finally:
        db.close()
        engine.dispose()


def test_dispatch_repair_marks_timestamp_only_after_queue_success(monkeypatch):
    engine, db = _db()
    try:
        _job, _current, _stale, _outsider, task = _seed_job_with_candidates(db)
        sent = []
        monkeypatch.setattr(
            job_reevaluations.queue,
            "send_job_reevaluation",
            lambda task_id: sent.append(task_id) or "message-1",
        )

        assert job_reevaluations.dispatch_undispatched_job_reevaluations(db) == 1
        db.refresh(task)
        assert sent == [task.id]
        assert task.queue_dispatched_at is not None
        assert job_reevaluations.dispatch_undispatched_job_reevaluations(db) == 0
    finally:
        db.close()
        engine.dispose()

def test_isolated_ranking_evaluation_persists_after_db_free_model_call(monkeypatch):
    engine, db = _db()
    try:
        job = Job(
            title="Platform Engineer",
            description="AWS, Python y automatización.",
            owner_sub="owner-1",
            evaluation_version=3,
        )
        candidate = Candidate(
            name="Parallel Candidate",
            owner_sub="owner-1",
        )
        db.add_all([job, candidate])
        db.commit()
        job_id = job.id
        candidate_id = candidate.id
        db.rollback()

        monkeypatch.setattr(
            job_reevaluations,
            "SessionLocal",
            lambda: Session(engine),
        )
        calls = []

        def fake_evidence(*, candidate_id, evaluation_text):
            calls.append((candidate_id, evaluation_text))
            return {
                "match_score": 91,
                "recommendation": "STRONG_MATCH",
                "summary": (
                    "La persona candidata cumple ampliamente los requisitos "
                    "principales de la vacante evaluada."
                ),
                "strengths": ["AWS"],
                "gaps": [],
                "requirements": [],
                "status": "COMPLETED",
                "error_message": None,
            }, None

        monkeypatch.setattr(
            job_reevaluations.evaluations_service,
            "evaluate_candidate_evidence",
            fake_evidence,
        )

        completed = job_reevaluations._evaluate_candidate_in_isolated_session(
            candidate_id=candidate_id,
            job_id=job_id,
            owner_sub="owner-1",
            force_evaluation=False,
        )

        assert completed is True
        assert calls and calls[0][0] == candidate_id
        db.expire_all()
        evaluation = (
            db.query(Evaluation)
            .filter(
                Evaluation.job_id == job_id,
                Evaluation.candidate_id == candidate_id,
            )
            .one()
        )
        assert evaluation.status == "COMPLETED"
        assert evaluation.match_score == 91
        assert evaluation.job_evaluation_version == 3
    finally:
        db.close()
        engine.dispose()


def test_parallel_ranking_evaluations_use_sequential_blocks_of_at_most_ten(monkeypatch):
    engine, db = _db()
    try:
        executors = []
        evaluated = []

        class RecordingExecutor:
            def __init__(self, *, max_workers, thread_name_prefix=None):
                self.max_workers = max_workers
                self.submissions = []

            def __enter__(self):
                executors.append(self)
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def submit(self, fn, **kwargs):
                self.submissions.append(list(kwargs["candidate_batch"]))
                future = Future()
                try:
                    future.set_result(fn(**kwargs))
                except Exception as exc:
                    future.set_exception(exc)
                return future

        monkeypatch.setattr(job_reevaluations, "ThreadPoolExecutor", RecordingExecutor)
        monkeypatch.setattr(
            job_reevaluations,
            "get_ranking_evaluation_batch_size",
            lambda: 10,
        )
        monkeypatch.setattr(
            job_reevaluations,
            "get_ranking_evaluation_concurrency",
            lambda: 10,
        )
        monkeypatch.setattr(
            job_reevaluations,
            "_evaluate_candidate_in_isolated_session",
            lambda **kwargs: evaluated.append(kwargs["candidate_id"]) or True,
        )

        candidate_ids = [f"candidate-{index:02d}" for index in range(23)]
        failures = job_reevaluations._run_parallel_candidate_evaluations(
            db,
            task_id="task-1",
            processing_token=None,
            job_id="job-1",
            owner_sub="owner-1",
            candidate_ids=candidate_ids,
            force_evaluation=False,
        )

        assert failures == []
        assert [executor.max_workers for executor in executors] == [3]
        assert executors[0].submissions == [
            candidate_ids[:10],
            candidate_ids[10:20],
            candidate_ids[20:],
        ]
        assert evaluated == candidate_ids
    finally:
        db.close()
        engine.dispose()


def test_sequential_batch_continues_after_candidate_failure(monkeypatch):
    evaluated = []

    def fake_evaluation(**kwargs):
        candidate_id = kwargs["candidate_id"]
        evaluated.append(candidate_id)
        if candidate_id == "second":
            raise RuntimeError("model unavailable")
        return candidate_id != "third"

    monkeypatch.setattr(
        job_reevaluations,
        "_evaluate_candidate_in_isolated_session",
        fake_evaluation,
    )
    failures = job_reevaluations._evaluate_sequential_batch(
        candidate_batch=["first", "second", "third", "fourth"],
        job_id="job-1",
        owner_sub="owner-1",
        force_evaluation=False,
    )
    assert evaluated == ["first", "second", "third", "fourth"]
    assert failures == ["second", "third"]
