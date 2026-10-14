"""Database-level tests for durable, non-destructive termination requests."""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import UserProfile, EmployeeTerminationRequest
from app.domains.employees.termination import TerminationError, TerminationReason
from app.domains.employees.termination_requests import request_termination


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[
        UserProfile.__table__, EmployeeTerminationRequest.__table__
    ])
    with sessionmaker(bind=engine)() as session:
        yield session
    engine.dispose()


def test_request_is_durable_and_idempotent_without_disabling_employee(db):
    employee = UserProfile(
        id="fake-employee-001", email="synthetic@example.invalid",
        odoo_employee_id="42", first_name="Test", status="ACTIVE"
    )
    db.add(employee)
    db.commit()
    args = dict(
        employee_id=employee.id, effective_date=date(2026, 10, 14),
        reason=TerminationReason.RESIGNATION,
        notes="Renuncia voluntaria documentada para pruebas.",
        actor_sub="synthetic-admin", idempotency_key="test-request-unique-001",
    )
    first = request_termination(db, **args)
    second = request_termination(db, **args)
    assert first.id == second.id
    assert first.status == "PENDING"
    assert employee.status == "ACTIVE"
    assert db.query(EmployeeTerminationRequest).count() == 1
    with pytest.raises(TerminationError):
        request_termination(db, **(args | {"idempotency_key": "different-request-002"}))


def test_unlinked_employee_cannot_request_termination(db):
    db.add(UserProfile(id="fake-employee-002", email="unlinked@example.invalid", status="ACTIVE"))
    db.commit()
    with pytest.raises(TerminationError):
        request_termination(
            db, employee_id="fake-employee-002", effective_date=date(2026, 10, 14),
            reason=TerminationReason.OTHER, notes="Solicitud de prueba sin vínculo a Odoo.",
            actor_sub="synthetic-admin", idempotency_key="test-unlinked-001",
        )
    assert db.query(EmployeeTerminationRequest).count() == 0
