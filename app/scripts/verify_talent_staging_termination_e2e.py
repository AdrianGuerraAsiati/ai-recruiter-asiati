"""Manual, synthetic-only real Odoo+Cognito E2E using ephemeral PostgreSQL.

The GitHub workflow is workflow_dispatch ONLY. Nothing here is invoked by the
production API/worker. This file never creates or deletes Odoo employees.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, time

import boto3
from sqlalchemy.orm import Session

from app.db import Base, get_engine
from app.domains.employees.termination_executor import (
    _assert_isolated_talent_database, execute_termination,
)
from app.domains.odoo_sync.staging import build_staging_client
from app.models import EmployeeTerminationRequest, UserProfile
from app.scripts.termination_staging_preflight import checks


SYNTHETIC_ODOO_NAME = "TALENT-E2E-TERMINATION-002"
SYNTHETIC_COGNITO_USERNAME = "talent-e2e-termination-002@example.invalid"
STAGING_POOL = "us-east-2_k6Q52r2rR"


def require_safe_inputs(*, employee_id: int, effective_date: date, execute: bool,
                        confirmation: str) -> None:
    if employee_id < 1 or effective_date > date.today():
        raise ValueError("Odoo employee ID or termination date is invalid.")
    if execute and confirmation != f"EXECUTE-E2E-TERMINATION-{employee_id}":
        raise ValueError("Staging write requires an exact explicit confirmation.")


def _subject(user: dict) -> str:
    values = [
        str(attr.get("Value") or "")
        for attr in user.get("UserAttributes", [])
        if attr.get("Name") == "sub"
    ]
    if len(values) != 1 or not values[0]:
        raise ValueError("Synthetic Cognito account has no unique subject.")
    return values[0]


class OdooRecorder:
    def __init__(self, inner):
        self.inner = inner
        self.database = inner.database
        self.base_url = inner.base_url
        self.writes = []

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def write(self, model, ids, values):
        self.writes.append((model, tuple(ids), tuple(sorted(values))))
        return self.inner.write(model, ids, values)


class CognitoRecorder:
    def __init__(self, inner):
        self.inner = inner
        self.disable_calls = 0

    def admin_get_user(self, **kwargs):
        return self.inner.admin_get_user(**kwargs)

    def admin_disable_user(self, **kwargs):
        self.disable_calls += 1
        return self.inner.admin_disable_user(**kwargs)


def run(*, employee_id: int, effective_date: date, execute: bool,
        confirmation: str) -> dict:
    require_safe_inputs(
        employee_id=employee_id, effective_date=effective_date,
        execute=execute, confirmation=confirmation,
    )
    readiness = checks()
    if not all(readiness.values()):
        raise ValueError("Dedicated staging prerequisites are NOT_READY.")

    # Verify the PostgreSQL DB engine BEFORE connecting to either remote system.
    engine = get_engine()
    with Session(engine) as session:
        _assert_isolated_talent_database(session)

    odoo = OdooRecorder(build_staging_client())
    health = odoo.healthcheck()
    if health.get("connected") is not True or health.get("uid") != 97:
        raise ValueError("Unexpected Odoo staging service identity.")

    employee_rows = odoo.search_read(
        "hr.employee", [["id", "=", employee_id]],
        fields=["id", "name", "active"], limit=2,
        context={"active_test": False},
    )
    if (len(employee_rows) != 1 or
            employee_rows[0]["name"] != SYNTHETIC_ODOO_NAME or
            employee_rows[0].get("active") is not True):
        raise ValueError("A fresh synthetic active Odoo employee is required.")
    contract_rows = odoo.search_read(
        "hr.contract", [["employee_id", "=", employee_id]],
        fields=["id", "name", "employee_id", "state", "date_start", "date_end"],
        limit=2,
    )
    if len(contract_rows) != 1 or contract_rows[0]["state"] != "open":
        raise ValueError("Exactly one open synthetic Odoo contract is required.")
    contract = contract_rows[0]
    owner = contract["employee_id"]
    if not isinstance(owner, (list, tuple)) or int(owner[0]) != employee_id:
        raise ValueError("Synthetic Odoo contract belongs to another employee.")
    if (contract.get("date_end") not in (False, None) or
            str(contract.get("date_start")) > effective_date.isoformat()):
        raise ValueError("Synthetic contract dates are unsuitable for termination.")

    cognito = CognitoRecorder(boto3.client("cognito-idp", region_name="us-east-2"))
    remote = cognito.admin_get_user(
        UserPoolId=STAGING_POOL, Username=SYNTHETIC_COGNITO_USERNAME,
    )
    if remote.get("Enabled") is not True:
        raise ValueError("A fresh ENABLED synthetic Cognito user is required.")
    synthetic_sub = _subject(remote)

    if not execute:
        return {
            "mode": "DRY_RUN", "odoo_synthetic_employee_id": employee_id,
            "odoo_synthetic_contract_id": contract["id"],
            "cognito_staging_identity_verified": True,
            "would_write_remote": True,
            "remote_writes": 0,
        }

    # These two tables are created ONLY in isolated, ephemeral E2E PostgreSQL.
    Base.metadata.create_all(
        engine, tables=[UserProfile.__table__, EmployeeTerminationRequest.__table__]
    )
    request_id = f"talent-e2e-termination-{employee_id}"
    profile_id = f"talent-e2e-employee-{employee_id}"
    with Session(engine, expire_on_commit=False) as session:
        session.add(UserProfile(
            id=profile_id, odoo_employee_id=str(employee_id),
            cognito_sub=synthetic_sub, email=SYNTHETIC_COGNITO_USERNAME,
            login_username="talent-e2e-002", status="ACTIVE",
        ))
        session.add(EmployeeTerminationRequest(
            id=request_id, employee_id=profile_id,
            odoo_employee_id=str(employee_id),
            idempotency_key=f"synthetic-stage-e2e-{employee_id}-{effective_date.isoformat()}",
            effective_date=datetime.combine(effective_date, time.min),
            reason="CONTRACT_END", notes="Synthetic only, authorized staging E2E",
            requested_by_sub="synthetic-stage-runner",
            status="PENDING", attempt_count=0, steps_completed=[],
        ))
        session.commit()
        first = execute_termination(
            session, request_id=request_id, odoo_client=odoo,
            cognito_client=cognito,
        )
        request = session.get(EmployeeTerminationRequest, request_id)
        profile = session.get(UserProfile, profile_id)
        expected_steps = ["odoo_closed_and_archived", "access_disabled"]
        if (first["status"] != "COMPLETED" or request.status != "COMPLETED"
                or request.steps_completed != expected_steps
                or request.attempt_count != 1 or profile.status != "DISABLED"):
            raise AssertionError("Persisted Talent workflow state failed verification.")

        writes_after_first = len(odoo.writes)
        cognito_disables_after_first = cognito.disable_calls
        repeated = execute_termination(
            session, request_id=request_id, odoo_client=odoo,
            cognito_client=cognito,
        )
        if (repeated != {"status": "COMPLETED", "idempotent": True}
                or len(odoo.writes) != writes_after_first
                or cognito.disable_calls != cognito_disables_after_first):
            raise AssertionError("Repeated staging E2E produced duplicate writes.")

    odoo_final = odoo.search_read(
        "hr.employee", [["id", "=", employee_id]],
        fields=["id", "active"], limit=2, context={"active_test": False},
    )
    contract_final = odoo.search_read(
        "hr.contract", [["id", "=", contract["id"]]],
        fields=["id", "state", "date_end"], limit=2,
    )
    cognito_final = cognito.admin_get_user(
        UserPoolId=STAGING_POOL, Username=SYNTHETIC_COGNITO_USERNAME,
    )
    if (len(odoo_final) != 1 or odoo_final[0]["active"] is not False
            or len(contract_final) != 1 or contract_final[0]["state"] != "close"
            or str(contract_final[0]["date_end"]) != effective_date.isoformat()
            or cognito_final.get("Enabled") is not False
            or _subject(cognito_final) != synthetic_sub):
        raise AssertionError("Odoo/Cognito post-execution reconciliation failed.")

    return {
        "mode": "EXECUTED", "odoo_employee_id": employee_id,
        "odoo_contract_id": contract["id"],
        "odoo_write_count": writes_after_first,
        "cognito_disable_count": cognito_disables_after_first,
        "talent_request_status": "COMPLETED",
        "checkpoint_count": len(expected_steps),
        "idempotent_retry": True,
        "remote_postconditions_verified": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Manual staging-only Talent termination E2E")
    parser.add_argument("--employee-id", type=int, required=True)
    parser.add_argument("--effective-date", type=date.fromisoformat, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()
    print(run(
        employee_id=args.employee_id, effective_date=args.effective_date,
        execute=args.execute, confirmation=args.confirm,
    ))


if __name__ == "__main__":
    main()
