"""Unit coverage for internal profiles and RBAC authorization."""

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.access_control import (
    ADMIN,
    EMPLOYEE,
    PERMISSION_DEFINITIONS,
    assign_role,
    ensure_rbac_catalog,
    resolve_principal,
)
from app.db import Base
from app.deps import require_permission, require_role
from app.models import Permission, Role, RolePermission, UserProfile, UserRole


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
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_new_authenticated_user_gets_employee_role_only(db):
    principal = resolve_principal(
        db,
        {
            "sub": "cognito-user-1",
            "email": "Employee@ASIATI.com.co",
            "email_verified": "true",
        },
    )

    assert principal["email"] == "employee@asiati.com.co"
    assert principal["roles"] == [EMPLOYEE]
    assert "training.consume" in principal["permissions"]
    assert "talent_id.attendance.read_own" in principal["permissions"]
    assert "talent_id.attendance.read_all" not in principal["permissions"]
    assert "employees.create" not in principal["permissions"]
    assert "integrations.manage" not in principal["permissions"]
    assert "employee_scores.read" not in principal["permissions"]


def test_admin_receives_all_system_permissions(db):
    resolve_principal(
        db,
        {"sub": "admin-1", "email": "admin@asiati.com.co"},
    )
    profile = db.query(UserProfile).filter_by(cognito_sub="admin-1").one()
    db.query(UserRole).filter(UserRole.user_id == profile.id).delete(
        synchronize_session=False
    )
    assign_role(db, profile, ADMIN)
    db.commit()

    principal = resolve_principal(
        db,
        {"sub": "admin-1", "email": "admin@asiati.com.co"},
    )

    assert principal["roles"] == [ADMIN]
    assert set(principal["permissions"]) == set(PERMISSION_DEFINITIONS)
    assert "integrations.manage" in principal["permissions"]
    assert "employee_scores.read" in principal["permissions"]
    assert "employee_scores.create" in principal["permissions"]
    assert "employee_scores.correct" in principal["permissions"]
    assert "employee_scores.export" in principal["permissions"]


def test_permission_and_role_dependencies_return_403_when_missing(db):
    employee = resolve_principal(
        db,
        {"sub": "employee-2", "email": "employee2@asiati.com.co"},
    )

    with pytest.raises(HTTPException) as permission_error:
        require_permission("employees.create")(employee)
    assert permission_error.value.status_code == 403

    with pytest.raises(HTTPException) as role_error:
        require_role(ADMIN)(employee)
    assert role_error.value.status_code == 403


def test_rbac_catalog_is_idempotent_and_contains_only_supported_roles(db):
    ensure_rbac_catalog(db)
    db.commit()
    first = (
        db.query(Role).count(),
        db.query(Permission).count(),
        db.query(RolePermission).count(),
    )

    ensure_rbac_catalog(db)
    db.commit()
    second = (
        db.query(Role).count(),
        db.query(Permission).count(),
        db.query(RolePermission).count(),
    )

    assert first == second
    assert {role.code for role in db.query(Role).all()} == {ADMIN, EMPLOYEE}


def test_bootstrap_admin_emails_are_promoted_from_employee(db, monkeypatch):
    monkeypatch.setenv(
        "RBAC_BOOTSTRAP_ADMIN_EMAILS",
        " sistemas@asiati.com.co , talentohumano@asiati.com.co ",
    )

    for sub, email in (
        ("systems-sub", "sistemas@asiati.com.co"),
        ("hr-sub", "talentohumano@asiati.com.co"),
    ):
        first = resolve_principal(db, {"sub": sub, "email": email})
        assert first["roles"] == [ADMIN]

        profile = db.query(UserProfile).filter_by(cognito_sub=sub).one()
        db.query(UserRole).filter(UserRole.user_id == profile.id).delete(
            synchronize_session=False
        )
        assign_role(db, profile, EMPLOYEE)
        db.commit()

        promoted = resolve_principal(db, {"sub": sub, "email": email})
        assert promoted["roles"] == [ADMIN]


def test_rbac_catalog_restores_missing_admin_grants(db):
    ensure_rbac_catalog(db)
    db.commit()

    db.query(RolePermission).filter(
        RolePermission.role_code == ADMIN,
        RolePermission.permission_code.in_(
            ("integrations.manage", "employee_scores.read")
        ),
    ).delete(synchronize_session=False)
    db.commit()

    ensure_rbac_catalog(db)
    db.commit()

    restored = {
        row.permission_code
        for row in db.query(RolePermission)
        .filter(
            RolePermission.role_code == ADMIN,
            RolePermission.permission_code.in_(
                ("integrations.manage", "employee_scores.read")
            ),
        )
        .all()
    }
    assert restored == {"integrations.manage", "employee_scores.read"}


def test_existing_principal_resolution_does_not_commit_when_nothing_changes(db, monkeypatch):
    resolve_principal(
        db,
        {"sub": "stable-user", "email": "stable@asiati.com.co"},
    )

    commits = []
    monkeypatch.setattr(db, "commit", lambda: commits.append(True))

    principal = resolve_principal(
        db,
        {"sub": "stable-user", "email": "stable@asiati.com.co"},
    )

    assert principal["roles"] == [EMPLOYEE]
    assert commits == []
