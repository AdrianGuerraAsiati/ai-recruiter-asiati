"""Employee contract delivery from Talent into Odoo."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.domains.odoo_sync import contract_delivery
from app.models import OdooContractSync, OdooEmployeeSync, UserProfile


class FakeOdooClient:
    def __init__(self, *, existing_contract=None, contract_type_match=True):
        self.existing_contract = existing_contract
        self.contract_type_match = contract_type_match
        self.created = []
        self.written = []
        self.searches = []

    def fields_get(self, model, **_kwargs):
        assert model == "hr.contract"
        return {
            "name": {"readonly": False, "type": "char"},
            "employee_id": {
                "readonly": False,
                "type": "many2one",
                "relation": "hr.employee",
            },
            "date_start": {"readonly": False, "type": "date"},
            "date_end": {"readonly": False, "type": "date"},
            "wage": {"readonly": False, "type": "monetary"},
            "contract_type_id": {
                "readonly": False,
                "type": "many2one",
                "relation": "hr.contract.type",
            },
            "state": {"readonly": True, "type": "selection"},
        }

    def search_read(self, model, domain, *, fields=None, limit=None):
        self.searches.append((model, domain, fields, limit))
        if model == "hr.contract.type":
            if self.contract_type_match:
                return [{"id": 9, "name": "Indefinido"}]
            return []
        if model != "hr.contract":
            return []

        if domain and domain[0][0] == "id":
            contract_id = int(domain[0][2])
            if self.existing_contract and int(self.existing_contract["id"]) == contract_id:
                return [{"id": contract_id}]
            return []

        if self.existing_contract:
            return [dict(self.existing_contract)]
        return []

    def create(self, model, values):
        assert model == "hr.contract"
        self.created.append(dict(values))
        return 501

    def write(self, model, ids, values):
        assert model == "hr.contract"
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


def _sync(db, *, contract_record_id=None, employee_record_id="42", wage="3500000"):
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

    employee_sync = OdooEmployeeSync(
        employee_id=employee.id,
        idempotency_key="employee:employee-1",
        payload={},
        status="SYNCED" if employee_record_id else "PENDING",
        odoo_record_id=employee_record_id,
    )
    contract_sync = OdooContractSync(
        employee_id=employee.id,
        idempotency_key="contract:employee-1",
        payload={
            "schema_version": 1,
            "operation": "UPSERT_CONTRACT",
            "employee": {
                "name": "Ana Pérez",
                "email": "ana@asiati.com.co",
            },
            "contract": {
                "name": "Backend Developer - Ana Pérez",
                "contract_type": "Indefinido",
                "start_date": "2026-10-05",
                "end_date": None,
                "monthly_wage": wage,
            },
        },
        status="PENDING",
        odoo_record_id=contract_record_id,
    )
    db.add_all([employee_sync, contract_sync])
    db.commit()
    return contract_sync


def test_sync_creates_contract_for_synced_employee(db):
    sync = _sync(db)
    client = FakeOdooClient()

    result = contract_delivery.sync_contract_now(
        db,
        employee_id=sync.employee_id,
        client=client,
    )

    assert result["status"] == "SYNCED"
    assert result["action"] == "CREATED"
    assert result["odoo_record_id"] == "501"
    assert result["relations"]["employee_id"] == 42
    assert result["relations"]["contract_type_id"] == 9
    assert client.created == [
        {
            "name": "Backend Developer - Ana Pérez",
            "employee_id": 42,
            "date_start": "2026-10-05",
            "wage": 3500000.0,
            "contract_type_id": 9,
        }
    ]

    db.refresh(sync)
    assert sync.status == "SYNCED"
    assert sync.odoo_record_id == "501"
    assert sync.synced_at is not None


def test_sync_updates_existing_contract_idempotently(db):
    sync = _sync(db, contract_record_id="77")
    client = FakeOdooClient(
        existing_contract={
            "id": 77,
            "employee_id": [42, "Ana Pérez"],
            "date_start": "2026-10-05",
        }
    )

    result = contract_delivery.sync_contract_now(
        db,
        employee_id=sync.employee_id,
        client=client,
    )

    assert result["action"] == "UPDATED"
    assert result["odoo_record_id"] == "77"
    assert client.created == []
    assert client.written[0][0] == [77]


def test_contract_type_is_optional_when_odoo_has_no_exact_match(db):
    sync = _sync(db)
    client = FakeOdooClient(contract_type_match=False)

    result = contract_delivery.sync_contract_now(
        db,
        employee_id=sync.employee_id,
        client=client,
    )

    assert result["status"] == "SYNCED"
    assert result["relations"]["contract_type_matched"] is False
    assert "contract_type_id" not in client.created[0]


def test_contract_requires_employee_to_be_synced_first(db):
    sync = _sync(db, employee_record_id=None)

    with pytest.raises(contract_delivery.OdooContractDependencyError):
        contract_delivery.sync_contract_now(
            db,
            employee_id=sync.employee_id,
            client=FakeOdooClient(),
        )


def test_missing_wage_marks_contract_sync_failed(db):
    sync = _sync(db, wage=None)

    with pytest.raises(
        contract_delivery.OdooContractDeliveryError,
        match="monthly wage",
    ):
        contract_delivery.sync_contract_now(
            db,
            employee_id=sync.employee_id,
            client=FakeOdooClient(),
        )

    db.refresh(sync)
    assert sync.status == "FAILED"
    assert sync.synced_at is None
