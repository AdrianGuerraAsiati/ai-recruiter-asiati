# Talent termination E2E — dedicated staging environment

## Status and boundaries

Odoo contract closure was validated on Odoo.sh **staging** against employee **1678**
and contract **6** on 2026-10-14. Both are now closed/archived and cannot
serve as a fresh contract-closure fixture.

This document describes a **separate**, manually invoked Talent workflow.
It is NOT a production feature flag, is NOT part of automatic deployment,
and must NEVER reuse Talent production's PostgreSQL database, employee
profiles, Cognito users or runtime AWS credentials.

- Talent production Cognito: `us-east-2_7rUnNHfEi` — forbidden for E2E writes.
- Dedicated Cognito pool: `us-east-2_k6Q52r2rR`
  (`ai-recruiter-termination-e2e-staging`), created with admin-only registration.
- Odoo.sh staging: `https://asiati-test160526-39554181.dev.odoo.com`,
  database `asiati-test160526-39554181`.
- The ONLY permitted Talent E2E PostgreSQL database name:
  `talent_e2e_terminations`.
- No public Talent staging endpoint is needed for this adapter-only integration
  test. Use a short-lived isolated runner on a **separate staging host/CI agent**,
  not the production Lightsail machine.

## Required infrastructure (not provisioned by this PR)

1. A separate isolated PostgreSQL instance/database named
   `talent_e2e_terminations`, accessible only by the manual E2E runner.
   Create the database **empty**; never restore a production backup.
   Enforce private network access, dedicated credentials and no public port.
2. A restricted staging IAM runtime identity: permission to read ONLY the
   existing staging Odoo secret (`/ai-recruiter/staging/odoo`) and to call
   `cognito-idp:AdminGetUser` and `cognito-idp:AdminDisableUser` ONLY on
   `arn:aws:cognito-idp:us-east-2:890876258895:userpool/us-east-2_k6Q52r2rR`.
   Do not reuse production Roles Anywhere credentials from Lightsail.
3. An Odoo.sh staging fixture with `hr.employee.name` beginning with
   `TALENT-E2E-TERMINATION-` and exactly one **open** synthetic contract.
   Inspect payroll automations before creating or activating the fixture.
4. A synthetic Cognito user, **already created**, named
   `talent-e2e-termination-002@example.invalid` in the dedicated staging pool
   using `AdminCreateUser`, `MessageAction=SUPPRESS`. Store its immutable
   **sub** in the synthetic Talent `UserProfile`, and set the matching
   `UserProfile.email` to the literal Cognito username above. The portal's
   `login_username` is NOT the Cognito username; the executor resolves by
   email, verifies `sub`, then disables by email and re-reads the state.
   Never import real production users.
5. The isolated Talent DB needs the `user_profiles` and
   `employee_termination_requests` schemas. Use repository-defined schema
   and the additive SQL migration, only against the separate E2E database.

## Runtime and preflight (read-only)

Configure these variables ONLY in the isolated staging runner, not the
production API/worker:

```text
APP_ENV=staging
EMPLOYEE_TERMINATION_EXECUTION_ENABLED=true
EMPLOYEE_TERMINATION_STAGING_DATABASE=talent_e2e_terminations
DATABASE_URL=postgresql://<staging-only-db-user>:<redacted>@<staging-private-host>:5432/talent_e2e_terminations

COGNITO_USER_POOL_ID=us-east-2_7rUnNHfEi
COGNITO_STAGING_USER_POOL_ID=us-east-2_k6Q52r2rR

ODOO_STAGING_BASE_URL=https://asiati-test160526-39554181.dev.odoo.com
ODOO_STAGING_DATABASE=asiati-test160526-39554181
ODOO_STAGING_USERNAME=<staging-service-user>
ODOO_STAGING_SECRET_ID=/ai-recruiter/staging/odoo
```

The production Cognito pool ID is needed only to **reject a shared pool**;
the executor never calls Cognito using that pool ID. Odoo production
connection metadata, if present, is used only by `staging_settings()`
to prevent accidental host/database/secret reuse.

Run `python -m app.scripts.termination_staging_preflight`.
It performs **no DB connection, network call or write** and shows only
`OK`/`NOT_READY` per condition. It exits nonzero if any guard fails.
Do not print environment variables, credentials or an unredacted DB URL.

## Test sequence

1. On a staging-only machine, run the preflight. A missing check is a blocker.
2. Confirm source Odoo fixture and a synthetic Cognito user are each unique.
3. Create a synthetic `UserProfile` and `EmployeeTerminationRequest`
   only in `talent_e2e_terminations`, with the matching Odoo employee
   ID, Cognito `sub`, `PENDING` state, empty `steps_completed`, and
   a non-future effective date. Do not run a copied production data export.
4. Before invoking `execute_termination`, capture Odoo employee/contract,
   synthetic Cognito user enabled state, and E2E DB request status.
5. Execute ONCE with the dedicated staging clients and **explicit operator
   approval for staging writes**. Verify Odoo `close`, `date_end`,
   employee `active=False`, Cognito `Enabled=False`, Talent employee
   `DISABLED`, request `COMPLETED`, and both persisted checkpoints.
6. Execute a retry: expect `idempotent=True`, no second writes, no
   checkpoint changes and the original request/audit details retained.
7. Run the failure/retry suite (`test_employee_termination_checkpoint_recovery.py`)
   separately; those tests use **in-memory SQLite and stub clients only**.

Use a **fresh** Odoo staging fixture before retrying the real contract-closure
scenario. The old employee 1678/contract 6 fixture is already terminated.

## Hard safety gates

`execute_termination` refuses writes unless ALL are true:

- execution flag explicitly enabled **inside staging**,
- Odoo target is the dedicated staging host and database,
- SQLAlchemy session is PostgreSQL on exactly `talent_e2e_terminations`,
- if a Cognito account exists, Cognito pool is exactly
  `us-east-2_k6Q52r2rR`, distinct from the production pool.

Never set `EMPLOYEE_TERMINATION_EXECUTION_ENABLED=true` on the
production Lightsail API/worker or use the production DB connection.

**Remaining work:** provision dedicated PostgreSQL host/role, link synthetic
stage user and Odoo fixture, run an operator-approved end-to-end with
real staging services, and inspect Odoo payroll side effects. This PR
does **not** attest that those steps are complete.
