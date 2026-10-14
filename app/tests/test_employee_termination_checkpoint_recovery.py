"""Isolated termination workflow E2E: real SQLAlchemy commits, fake external systems.

No network, Odoo, Cognito, or production database credentials are used.
SQLite does not enforce PostgreSQL FOR UPDATE; concurrent workers need separate E2E.
"""
from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.domains.employees import termination_executor as executor
from app.domains.employees.termination import TerminationError
from app.domains.odoo_sync import staging
from app.models import EmployeeTerminationRequest, UserProfile


class CognitoStub:
    def __init__(self, failures=0):
        self.failures = failures
        self.calls = []

    def admin_disable_user(self, **kwargs):
        self.calls.append(kwargs)
        if self.failures:
            self.failures -= 1
            raise RuntimeError("simulated Cognito outage")
        return {}


@pytest.fixture
def environment(monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("EMPLOYEE_TERMINATION_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("COGNITO_STAGING_USER_POOL_ID", "us-east-2_k6Q52r2rR")
    monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-east-2_production")
    # These tests exercise transactional checkpoints against in-memory SQLite;
    # a separate set below verifies the non-bypassable production DB guard.
    monkeypatch.setattr(executor, "_assert_isolated_talent_database", lambda db: None)
    monkeypatch.setattr(
        staging,
        "staging_settings",
        lambda: SimpleNamespace(
            database="isolated-odoo-staging",
            base_url="https://isolated-staging.example.test",
        ),
    )
    return SimpleNamespace(
        database="isolated-odoo-staging",
        base_url="https://isolated-staging.example.test",
    )


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine, tables=[UserProfile.__table__, EmployeeTerminationRequest.__table__]
    )
    with Session(engine, expire_on_commit=False) as session:
        session.add(UserProfile(
            id="synthetic-employee", odoo_employee_id="1678",
            cognito_sub="synthetic-sub", email="synthetic@example.test",
            login_username="synthetic.account", status="ACTIVE",
        ))
        session.add(EmployeeTerminationRequest(
            id="synthetic-request", employee_id="synthetic-employee",
            odoo_employee_id="1678", idempotency_key="synthetic-key",
            effective_date=datetime(2026, 10, 14),
            reason="CONTRACT_END", notes="Synthetic integration testing",
            requested_by_sub="synthetic-admin", status="PENDING",
            attempt_count=0, steps_completed=[],
        ))
        session.commit()
        yield session
    engine.dispose()


def state(db):
    db.expire_all()
    request = db.get(EmployeeTerminationRequest, "synthetic-request")
    employee = db.get(UserProfile, "synthetic-employee")
    return request, employee


def test_success_then_idempotent_retry_with_checkpoints(db, environment, monkeypatch):
    odoo_calls = []
    monkeypatch.setattr(executor, "close_contract_and_archive", lambda *a, **kw: odoo_calls.append(kw))
    cognito = CognitoStub()
    result = executor.execute_termination(
        db, request_id="synthetic-request", odoo_client=environment,
        cognito_client=cognito,
    )
    request, employee = state(db)
    assert result["status"] == "COMPLETED"
    assert request.status == "COMPLETED"
    assert request.steps_completed == ["odoo_closed_and_archived", "access_disabled"]
    assert employee.status == "DISABLED"
    assert request.attempt_count == 1
    assert len(odoo_calls) == 1
    assert cognito.calls == [{
        "UserPoolId": "us-east-2_k6Q52r2rR",
        "Username": "synthetic-sub",
    }]
    second = executor.execute_termination(
        db, request_id="synthetic-request", odoo_client=environment,
        cognito_client=cognito,
    )
    assert second == {"status": "COMPLETED", "idempotent": True}
    assert len(odoo_calls) == len(cognito.calls) == 1
    assert state(db)[0].attempt_count == 1


def test_cognito_failure_preserves_odoo_checkpoint_then_recovers(
    db, environment, monkeypatch
):
    odoo_calls = []
    monkeypatch.setattr(executor, "close_contract_and_archive", lambda *a, **kw: odoo_calls.append(kw))
    cognito = CognitoStub(failures=1)
    with pytest.raises(RuntimeError, match="simulated Cognito outage"):
        executor.execute_termination(
            db, request_id="synthetic-request",
            odoo_client=environment, cognito_client=cognito,
        )
    request, employee = state(db)
    assert request.status == "FAILED"
    assert request.steps_completed == ["odoo_closed_and_archived"]
    assert request.attempt_count == 1
    assert employee.status == "ACTIVE"
    assert request.last_error == "RuntimeError"

    result = executor.execute_termination(
        db, request_id="synthetic-request",
        odoo_client=environment, cognito_client=cognito,
    )
    request, employee = state(db)
    assert result["status"] == request.status == "COMPLETED"
    assert request.steps_completed == ["odoo_closed_and_archived", "access_disabled"]
    assert request.attempt_count == 2
    assert employee.status == "DISABLED"
    assert len(odoo_calls) == 1
    assert len(cognito.calls) == 2


def test_odoo_failure_retries_without_marking_checkpoint(db, environment, monkeypatch):
    calls = []

    def flaky_odoo(*args, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise RuntimeError("simulated Odoo network failure")

    monkeypatch.setattr(executor, "close_contract_and_archive", flaky_odoo)
    cognito = CognitoStub()
    with pytest.raises(RuntimeError, match="simulated Odoo network failure"):
        executor.execute_termination(
            db, request_id="synthetic-request",
            odoo_client=environment, cognito_client=cognito,
        )
    request, employee = state(db)
    assert request.status == "FAILED"
    assert request.steps_completed == []
    assert employee.status == "ACTIVE"
    assert cognito.calls == []
    executor.execute_termination(
        db, request_id="synthetic-request",
        odoo_client=environment, cognito_client=cognito,
    )
    request, employee = state(db)
    assert request.status == "COMPLETED"
    assert request.attempt_count == 2
    assert employee.status == "DISABLED"
    assert len(calls) == 2


@pytest.mark.parametrize("staging_pool,production_pool", [
    ("", "us-east-2_production"),
    ("us-east-2_production", "us-east-2_production"),
    ("us-east-2_k6Q52r2rR", ""),
])
def test_missing_or_shared_cognito_pool_is_blocked_before_odoo(
    db, environment, monkeypatch, staging_pool, production_pool
):
    monkeypatch.setenv("COGNITO_STAGING_USER_POOL_ID", staging_pool)
    monkeypatch.setenv("COGNITO_USER_POOL_ID", production_pool)
    odoo_calls = []
    monkeypatch.setattr(executor, "close_contract_and_archive", lambda *a, **kw: odoo_calls.append(kw))
    with pytest.raises(TerminationError, match="User Pool Cognito de staging"):
        executor.execute_termination(
            db, request_id="synthetic-request",
            odoo_client=environment, cognito_client=CognitoStub(),
        )
    request, employee = state(db)
    assert request.status == "PENDING"
    assert request.attempt_count == 0
    assert employee.status == "ACTIVE"
    assert not odoo_calls


def test_unlinked_employee_is_rejected_before_side_effects(db, environment, monkeypatch):
    employee = db.get(UserProfile, "synthetic-employee")
    employee.odoo_employee_id = "9999"
    db.commit()
    odoo_calls = []
    monkeypatch.setattr(executor, "close_contract_and_archive", lambda *a, **kw: odoo_calls.append(kw))
    with pytest.raises(TerminationError, match="identidad de Odoo"):
        executor.execute_termination(
            db, request_id="synthetic-request",
            odoo_client=environment, cognito_client=CognitoStub(),
        )
    assert state(db)[0].status == "PENDING"
    assert not odoo_calls


def test_imported_employee_without_cognito_can_finish(db, environment, monkeypatch):
    employee = db.get(UserProfile, "synthetic-employee")
    employee.cognito_sub = None
    db.commit()
    monkeypatch.delenv("COGNITO_STAGING_USER_POOL_ID")
    calls = []
    monkeypatch.setattr(executor, "close_contract_and_archive", lambda *a, **kw: calls.append(kw))
    cognito = CognitoStub()
    executor.execute_termination(
        db, request_id="synthetic-request",
        odoo_client=environment, cognito_client=cognito,
    )
    request, employee = state(db)
    assert request.status == "COMPLETED"
    assert employee.status == "DISABLED"
    assert len(calls) == 1
    assert cognito.calls == []


def test_in_progress_request_cannot_run_twice(db, environment, monkeypatch):
    request = db.get(EmployeeTerminationRequest, "synthetic-request")
    request.status = "IN_PROGRESS"
    db.commit()
    writes = []
    monkeypatch.setattr(executor, "close_contract_and_archive", lambda *a, **kw: writes.append(kw))
    with pytest.raises(TerminationError, match="ya está siendo procesada"):
        executor.execute_termination(
            db, request_id="synthetic-request",
            odoo_client=environment, cognito_client=CognitoStub(),
        )
    assert state(db)[0].status == "IN_PROGRESS"
    assert not writes


def test_missing_request_has_no_external_side_effect(db, environment, monkeypatch):
    writes = []
    monkeypatch.setattr(executor, "close_contract_and_archive", lambda *a, **kw: writes.append(kw))
    with pytest.raises(TerminationError, match="inexistente"):
        executor.execute_termination(
            db, request_id="nonexistent",
            odoo_client=environment, cognito_client=CognitoStub(),
        )
    assert not writes


def test_staging_database_guard_requires_explicit_database_name(db, monkeypatch):
    monkeypatch.delenv("EMPLOYEE_TERMINATION_STAGING_DATABASE", raising=False)
    with pytest.raises(TerminationError, match="E2E dedicada"):
        executor._assert_isolated_talent_database(db)


def test_staging_database_guard_rejects_sqlite(db, monkeypatch):
    monkeypatch.setenv("EMPLOYEE_TERMINATION_STAGING_DATABASE", "talent_e2e_terminations")
    with pytest.raises(TerminationError, match="E2E aislada"):
        executor._assert_isolated_talent_database(db)


@pytest.mark.parametrize("dialect,database", [
    ("postgresql", "ai_recruiter"),
    ("postgresql", "talent_e2e_terminations_backup"),
    ("sqlite", "talent_e2e_terminations"),
])
def test_staging_database_guard_rejects_wrong_engine(monkeypatch, dialect, database):
    monkeypatch.setenv("EMPLOYEE_TERMINATION_STAGING_DATABASE", "talent_e2e_terminations")
    bind = SimpleNamespace(dialect=SimpleNamespace(name=dialect),
                           url=SimpleNamespace(database=database))
    fake_db = SimpleNamespace(get_bind=lambda: bind)
    with pytest.raises(TerminationError, match="E2E aislada"):
        executor._assert_isolated_talent_database(fake_db)


def test_staging_database_guard_accepts_only_dedicated_postgres(monkeypatch):
    monkeypatch.setenv("EMPLOYEE_TERMINATION_STAGING_DATABASE", "talent_e2e_terminations")
    bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"),
                           url=SimpleNamespace(database="talent_e2e_terminations"))
    fake_db = SimpleNamespace(get_bind=lambda: bind)
    executor._assert_isolated_talent_database(fake_db)
