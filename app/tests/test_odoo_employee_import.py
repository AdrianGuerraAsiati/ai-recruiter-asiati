"""Odoo employee directory import tests."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.access_control import EMPLOYEE, assign_role, ensure_rbac_catalog
from app.db import Base
from app.domains.odoo_sync import employee_import
from app.models import Permission, Role, RolePermission, UserProfile, UserRole


class FakeOdooClient:
    def __init__(self, rows):
        self.rows = rows
        self.searches = []

    def fields_get(self, model, **_kwargs):
        assert model == "hr.employee"
        return {
            "name": {"type": "char"},
            "work_email": {"type": "char"},
            "job_title": {"type": "char"},
            "job_id": {"type": "many2one", "relation": "hr.job"},
            "department_id": {"type": "many2one", "relation": "hr.department"},
            "active": {"type": "boolean"},
        }

    def search_read(self, model, domain, *, fields=None, limit=None):
        assert model == "hr.employee"
        self.searches.append((domain, fields, limit))
        return [dict(row) for row in self.rows]


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Role.__table__,
            Permission.__table__,
            UserProfile.__table__,
            UserRole.__table__,
            RolePermission.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    session = Session()
    ensure_rbac_catalog(session)
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_imports_all_odoo_employees_without_creating_access(db):
    client = FakeOdooClient(
        [
            {
                "id": 10,
                "name": "Ana Pérez",
                "work_email": "ana@asiati.com.co",
                "job_title": "Desarrolladora",
                "department_id": [2, "Tecnología"],
                "active": True,
            },
            {
                "id": 11,
                "name": "Carlos Ruiz",
                "work_email": False,
                "job_id": [7, "Mensajero"],
                "department_id": [3, "Operaciones"],
                "active": True,
            },
            {
                "id": 12,
                "name": "Laura Gómez",
                "work_email": "laura@asiati.com.co",
                "job_title": "Analista",
                "department_id": [4, "Administración"],
                "active": False,
            },
        ]
    )

    result = employee_import.sync_employees_from_odoo(
        db,
        client=client,
        actor_sub="admin-sub",
    )

    assert result == {
        "source": "ODOO",
        "model": "hr.employee",
        "total": 3,
        "created": 3,
        "updated": 0,
        "linked_by_email": 0,
        "without_work_email": 1,
        "duplicate_email_rows": 0,
        "inactive": 1,
    }

    profiles = db.query(UserProfile).order_by(UserProfile.odoo_employee_id).all()
    assert len(profiles) == 3
    assert profiles[0].email == "ana@asiati.com.co"
    assert profiles[0].cognito_sub is None
    assert profiles[0].first_name == "Ana Pérez"
    assert profiles[0].department == "Tecnología"
    assert profiles[0].onboarding_status == "NOT_REQUIRED"
    assert profiles[1].email is None
    assert profiles[1].job_title == "Mensajero"
    assert profiles[2].status == "DISABLED"
    assert db.query(UserRole).count() == 3


def test_import_is_idempotent_by_odoo_employee_id(db):
    client = FakeOdooClient(
        [
            {
                "id": 20,
                "name": "Empleado Uno",
                "work_email": "uno@asiati.com.co",
                "job_title": "Analista",
                "department_id": [1, "Operaciones"],
                "active": True,
            }
        ]
    )

    first = employee_import.sync_employees_from_odoo(db, client=client)
    second = employee_import.sync_employees_from_odoo(db, client=client)

    assert first["created"] == 1
    assert second["created"] == 0
    assert second["updated"] == 1
    assert db.query(UserProfile).count() == 1


def test_import_links_existing_talent_profile_by_unique_work_email(db):
    existing = UserProfile(
        cognito_sub="sub-existing",
        email="existing@asiati.com.co",
        login_username="existing.user",
        first_name="Nombre Local",
        last_name="Apellido Local",
        job_title="Cargo anterior",
        department="Área anterior",
        onboarding_status="COMPLETED",
        status="ACTIVE",
    )
    db.add(existing)
    db.flush()
    assign_role(db, existing, EMPLOYEE)
    db.commit()

    client = FakeOdooClient(
        [
            {
                "id": 30,
                "name": "Nombre Odoo",
                "work_email": "EXISTING@ASIATI.COM.CO",
                "job_title": "Nuevo cargo",
                "department_id": [5, "Nueva área"],
                "active": False,
            }
        ]
    )

    result = employee_import.sync_employees_from_odoo(db, client=client)

    db.refresh(existing)
    assert result["created"] == 0
    assert result["updated"] == 1
    assert result["linked_by_email"] == 1
    assert existing.odoo_employee_id == "30"
    assert existing.first_name == "Nombre Local"
    assert existing.last_name == "Apellido Local"
    assert existing.job_title == "Nuevo cargo"
    assert existing.department == "Nueva área"
    assert existing.status == "ACTIVE"
    assert existing.onboarding_status == "COMPLETED"
    assert db.query(UserProfile).count() == 1


def test_duplicate_odoo_work_emails_do_not_collapse_people(db):
    client = FakeOdooClient(
        [
            {
                "id": 40,
                "name": "Persona A",
                "work_email": "shared@asiati.com.co",
                "active": True,
            },
            {
                "id": 41,
                "name": "Persona B",
                "work_email": "shared@asiati.com.co",
                "active": True,
            },
        ]
    )

    result = employee_import.sync_employees_from_odoo(db, client=client)
    second = employee_import.sync_employees_from_odoo(db, client=client)

    assert result["created"] == 2
    assert result["duplicate_email_rows"] == 2
    assert second["created"] == 0
    assert second["updated"] == 2
    profiles = db.query(UserProfile).order_by(UserProfile.odoo_employee_id).all()
    assert [profile.odoo_employee_id for profile in profiles] == ["40", "41"]
    assert [profile.email for profile in profiles] == [None, None]
