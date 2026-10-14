"""Auditable employee termination with checkpoints and post-write verification.

Disabled by default. The execution path is restricted to staging/test until
the company's Odoo 18 schema and payroll policy are certified.
"""
import os
from urllib.parse import urlparse

from app.domains.employees.termination import TerminationError
from app.domains.odoo_sync.termination_delivery import close_contract_and_archive
from app.models import EmployeeTerminationRequest, UserProfile


def _staging_cognito_pool_id() -> str:
    """Fail closed: Cognito access changes must never target the production pool."""
    staging_pool = os.getenv("COGNITO_STAGING_USER_POOL_ID", "").strip()
    production_pool = os.getenv("COGNITO_USER_POOL_ID", "").strip()
    if (staging_pool != "us-east-2_k6Q52r2rR" or not production_pool
            or staging_pool == production_pool):
        raise TerminationError(
            "Se requiere un User Pool Cognito de staging distinto del de producción."
        )
    return staging_pool


def _verified_staging_cognito_user(client, *, pool_id: str, username: str, expected_sub: str):
    """Resolve the real Cognito username and verify its immutable subject."""
    result = client.admin_get_user(UserPoolId=pool_id, Username=username)
    subjects = [
        str(attr.get("Value") or "")
        for attr in result.get("UserAttributes", [])
        if attr.get("Name") == "sub"
    ]
    if len(subjects) != 1 or subjects[0] != expected_sub:
        raise TerminationError("La identidad Cognito no coincide: retiro bloqueado.")
    return result


def _assert_isolated_talent_database(db):
    """Fail closed on non-PostgreSQL or production Talent SQLAlchemy sessions.

    The dedicated E2E PostgreSQL database must never be the normal Talent DB.
    No network queries or external side effects take place in this guard.
    """
    expected = os.getenv("EMPLOYEE_TERMINATION_STAGING_DATABASE", "").strip()
    if expected != "talent_e2e_terminations":
        raise TerminationError("Base Talent E2E dedicada no configurada.")
    try:
        bind = db.get_bind()
        dialect = bind.dialect.name
        actual = bind.url.database
    except (AttributeError, TypeError, ValueError) as exc:
        raise TerminationError("No se pudo verificar la base Talent Staging.") from exc
    if dialect != "postgresql" or actual != expected:
        raise TerminationError("Ejecución bloqueada: la base Talent no es la E2E aislada.")


def execute_termination(db, *, request_id: str, odoo_client, cognito_client):
    if os.getenv("EMPLOYEE_TERMINATION_EXECUTION_ENABLED") != "true":
        raise TerminationError("Ejecución de retiros deshabilitada.")
    if os.getenv("APP_ENV", "").lower() not in {"staging", "test"}:
        raise TerminationError("Solo se permite ejecutar retiros en staging.")

    # Do not trust APP_ENV alone: the injected client must target the separate staging DB.
    from app.domains.odoo_sync.staging import staging_settings
    target = staging_settings()
    if (target.database != "asiati-test160526-39554181"
            or urlparse(target.base_url).hostname
            != "asiati-test160526-39554181.dev.odoo.com"):
        raise TerminationError("La configuración Odoo no es el staging E2E autorizado.")
    client_db = getattr(odoo_client, "database", None)
    client_url = getattr(odoo_client, "base_url", None)
    if client_db != target.database or (urlparse(str(client_url)).hostname != urlparse(target.base_url).hostname):
        raise TerminationError("El cliente Odoo no apunta exclusivamente a staging.")

    _assert_isolated_talent_database(db)

    request = db.query(EmployeeTerminationRequest).filter(
        EmployeeTerminationRequest.id == request_id
    ).with_for_update().one_or_none()
    if request is None:
        raise TerminationError("Solicitud de retiro inexistente.")
    employee = db.query(UserProfile).filter(
        UserProfile.id == request.employee_id
    ).with_for_update().one_or_none()
    if employee is None or str(employee.odoo_employee_id) != request.odoo_employee_id:
        raise TerminationError("La identidad de Odoo cambió: revisión manual requerida.")
    if request.status == "COMPLETED":
        return {"status": "COMPLETED", "idempotent": True}
    if request.status == "IN_PROGRESS":
        raise TerminationError("La solicitud ya está siendo procesada.")

    # Resolve a separate Cognito target BEFORE the first Odoo write. Imported
    # employees without a Cognito account do not need a pool.
    staging_pool_id = _staging_cognito_pool_id() if employee.cognito_sub else None
    if employee.cognito_sub:
        # Talent's display login_username is NOT the username in Cognito.
        # The existing provisioning service creates Cognito users using email.
        if not employee.email:
            raise TerminationError("Cuenta Cognito sin correo vinculado.")
        _verified_staging_cognito_user(
            cognito_client, pool_id=staging_pool_id,
            username=employee.email, expected_sub=employee.cognito_sub,
        )

    request.status = "IN_PROGRESS"
    request.attempt_count = int(request.attempt_count or 0) + 1
    request.last_error = None
    db.commit()

    try:
        steps = list(request.steps_completed or [])

        if "odoo_closed_and_archived" not in steps:
            close_contract_and_archive(
                odoo_client,
                employee_odoo_id=request.odoo_employee_id,
                effective_date=request.effective_date.date(),
            )
            # Assign a fresh list: mutating an already-assigned JSON list is not
            # reliably detected by SQLAlchemy after a commit.
            steps = [*steps, "odoo_closed_and_archived"]
            request.steps_completed = steps
            db.commit()

        if "access_disabled" not in steps:
            # Imported Odoo employees may have no Cognito account.
            if employee.cognito_sub:
                # Check identity again before mutation; Cognito's AdminDisableUser
                # requires the actual username (Talent creates it using email).
                current_user = _verified_staging_cognito_user(
                    cognito_client, pool_id=staging_pool_id,
                    username=employee.email, expected_sub=employee.cognito_sub,
                )
                if current_user.get("Enabled") is not False:
                    cognito_client.admin_disable_user(
                        UserPoolId=staging_pool_id, Username=employee.email
                    )
                updated_user = _verified_staging_cognito_user(
                    cognito_client, pool_id=staging_pool_id,
                    username=employee.email, expected_sub=employee.cognito_sub,
                )
                if updated_user.get("Enabled") is not False:
                    raise TerminationError("Cognito no confirmó el bloqueo del acceso.")
            employee.status = "DISABLED"
            steps = [*steps, "access_disabled"]
            request.steps_completed = steps
            db.commit()

        request.status = "COMPLETED"
        request.last_error = None
        db.commit()
        return {"status": "COMPLETED", "idempotent": False,
                "steps_completed": list(request.steps_completed)}
    except Exception as exc:
        db.rollback()
        request.status = "FAILED"
        request.last_error = type(exc).__name__[:100]
        db.commit()
        raise
