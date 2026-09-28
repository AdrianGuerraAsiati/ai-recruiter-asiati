"""Employee delivery from aiRecruiter outbox into Odoo."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.domains.odoo_sync import employee_delivery
from app.models import OdooEmployeeSync, UserProfile


class FakeOdooClient:
    def __init__(
        self,
        *,
        existing_employee=None,
        duplicate_email=False,
        include_relations=True,
    ):
        self.existing_employee = existing_employee
        self.duplicate_email = duplicate_email
        self.include_relations = include_relations
        self.created = []
        self.written = []
        self.searches = []

    def fields_get(self, model, **_kwargs):
        assert model == "hr.employee"
        fields = {
            "name": {"readonly": False, "type": "char"},
            "work_email": {"readonly": False, "type": "char"},
            "job_title": {"readonly": False, "type": "char"},
            "private_phone": {"readonly": False, "type": "char"},
            "employee_type": {
                "readonly": False,
                "type": "selection",
                "selection": [["employee", "Employee"], ["contractor", "Contractor"]],
            },
            "legal_name": {"readonly": True, "type": "char"},
        }
        if self.include_relations:
            fields.update(
                {
                    "department_id": {
                        "readonly": False,
                        "type": "many2one",
                        "relation": "hr.department",
                    },
                    "job_id": {
                        "readonly": False,
                        "type": "many2one",
                        "relation": "hr.job",
                    },
                }
            )
        return fields

    def search_read(self, model, domain, *, fields=None, limit=None):
        self.searches.append((model, domain, fields, limit))
        if model == "hr.department":
            return [{"id": 11, "name": "Tecnología"}]
        if model == "hr.job":
            return [{"id": 22, "name": "Backend Developer"}]
        if model != "hr.employee":
            return []

        if domain and domain[0][0] == "id":
            employee_id = int(domain[0][2])
            if self.existing_employee and int(self.existing_employee["id"]) == employee_id:
                return [{"id": employee_id}]
            return []

        if self.duplicate_email:
            return [
                {"id": 31, "work_email": "ana@asiati.com.co"},
                {"id": 32, "work_email": "ana@asiati.com.co"},
            ]
        if self.existing_employee:
            return [dict(self.existing_employee)]
        return []

    def create(self, model, values):
        assert model == "hr.employee"
        self.created.append(dict(values))
        return 101

    def write(self, model, ids, values):
        assert model == "hr.employee"
        self.written.append((list(ids), dict(values)))
        return True


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _sync(db, *, record_id=None):
    employee = UserProfile(
        id="employee-1",
        cognito_sub="sub-employee-1",
        email="ana@asiati.com.co",
        first_name="Ana",
        last_name="Pérez",
        job_title="Backend Developer",
        department="Tecnología",
        onboarding_status="PENDING",
        status="ACTIVE",
    )
    db.add(employee)
    db.flush()
    sync = OdooEmployeeSync(
        employee_id=employee.id,
        idempotency_key="employee:employee-1",
        payload={
            "schema_version": 1,
            "operation": "UPSERT_EMPLOYEE",
            "employee": {
                "name": "Ana Pérez",
                "email": "ana@asiati.com.co",
                "job_title": "Backend Developer",
                "department": "Tecnología",
                "hire_date": "2026-09-28",
            },
            "candidate": {
                "name": "Ana Pérez",
                "email": "ana.personal@example.com",
                "phone": "+57 300 123 4567",
            },
            "job": {
                "title": "Backend Developer",
            },
        },
        status="PENDING",
        odoo_record_id=record_id,
    )
    db.add(sync)
    db.commit()
    return sync


def test_sync_creates_employee_with_safe_available_fields(db):
    sync = _sync(db)
    client = FakeOdooClient()

    result = employee_delivery.sync_employee_now(
        db,
        employee_id=sync.employee_id,
        client=client,
    )

    assert result["status"] == "SYNCED"
    assert result["action"] == "CREATED"
    assert result["odoo_record_id"] == "101"
    assert result["attempt_count"] == 1
    assert result["relations"]["department_id"] == 11
    assert result["relations"]["job_id"] == 22
    assert client.created == [
        {
            "name": "Ana Pérez",
            "work_email": "ana@asiati.com.co",
            "job_title": "Backend Developer",
            "private_phone": "+57 300 123 4567",
            "employee_type": "employee",
            "department_id": 11,
            "job_id": 22,
        }
    ]

    db.refresh(sync)
    assert sync.status == "SYNCED"
    assert sync.odoo_record_id == "101"
    assert sync.last_error is None
    assert sync.synced_at is not None


def test_sync_updates_stored_odoo_employee_instead_of_creating(db):
    sync = _sync(db, record_id="77")
    client = FakeOdooClient(
        existing_employee={"id": 77, "work_email": "ana@asiati.com.co"}
    )

    result = employee_delivery.sync_employee_now(
        db,
        employee_id=sync.employee_id,
        client=client,
    )

    assert result["action"] == "UPDATED"
    assert result["odoo_record_id"] == "77"
    assert client.created == []
    assert client.written
    assert client.written[0][0] == [77]


def test_sync_uses_email_to_update_existing_employee(db):
    sync = _sync(db)
    client = FakeOdooClient(
        existing_employee={"id": 88, "work_email": "ana@asiati.com.co"}
    )

    result = employee_delivery.sync_employee_now(
        db,
        employee_id=sync.employee_id,
        client=client,
    )

    assert result["action"] == "UPDATED"
    assert result["odoo_record_id"] == "88"
    assert client.created == []


def test_sync_skips_relations_when_models_do_not_match(db):
    sync = _sync(db)
    client = FakeOdooClient(include_relations=False)

    result = employee_delivery.sync_employee_now(
        db,
        employee_id=sync.employee_id,
        client=client,
    )

    assert result["status"] == "SYNCED"
    assert result["relations"]["department_id"] is None
    assert result["relations"]["job_id"] is None
    assert "department_id" not in client.created[0]
    assert "job_id" not in client.created[0]


def test_duplicate_work_email_marks_sync_failed(db):
    sync = _sync(db)
    client = FakeOdooClient(duplicate_email=True)

    with pytest.raises(
        employee_delivery.OdooEmployeeDeliveryError,
        match="Multiple Odoo employees",
    ):
        employee_delivery.sync_employee_now(
            db,
            employee_id=sync.employee_id,
            client=client,
        )

    db.refresh(sync)
    assert sync.status == "FAILED"
    assert sync.attempt_count == 1
    assert "same work email" in sync.last_error
    assert sync.synced_at is None


def test_missing_employee_outbox_is_not_found(db):
    with pytest.raises(employee_delivery.OdooEmployeeSyncNotFound):
        employee_delivery.sync_employee_now(
            db,
            employee_id="missing",
            client=FakeOdooClient(),
        )
