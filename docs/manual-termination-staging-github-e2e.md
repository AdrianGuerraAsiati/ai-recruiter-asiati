# Manual Talent termination E2E with ephemeral GitHub PostgreSQL

This **workflow_dispatch-only** workflow is:
`.github/workflows/termination-staging-e2e.yml`.
It will not execute automatically on push, deploy, schedule or pull request.

The workflow needs NO new paid Lightsail instance. GitHub Actions creates
a fresh PostgreSQL 16 service inside the temporary runner. Its local password
has no use outside that runner and the database has no production data.
The database is discarded at the end of the job: its checkpoints prove
intra-run persistence and retry, **not cross-job durability**.
Cross-job recovery remains a separate persistent staging-DB test.

## AWS guardrails already provisioned

- GitHub IAM role: `AiRecruiterTerminationE2EStagingRole`.
- OIDC trust for repo ID `1387612825`, organization ID `333553246`,
  GitHub environment `termination-e2e-staging`, audience
  `sts.amazonaws.com`.
- Inline IAM policy allows only read of
  `/ai-recruiter/staging/odoo` and Cognito
  `AdminGetUser`/`AdminDisableUser` for pool `us-east-2_k6Q52r2rR`.
  No production Odoo secret or production Cognito pool permissions.
- The Cognito synthetic account
  `talent-e2e-termination-002@example.invalid` is created,
  initially enabled and never emailed (`MessageAction=SUPPRESS`).

## One-time fresh Odoo.sh staging fixture

The previous staging fixture employee 1678/contract 6 is ALREADY closed.
Do not reuse it.

In Odoo.sh **Test160526**, open `odoo-bin shell` and execute the
following Python (NOT in Bash or production Odoo). This intentionally
creates a second synthetic employee and running contract, potentially
triggering **staging** HR work-entry automations. Inspect those before
running; never run in a live production Odoo database.

```python
from datetime import date, datetime

assert env.cr.dbname == "asiati-test160526-39554181"
Employee = env["hr.employee"].sudo()
Contract = env["hr.contract"].sudo()
name = "TALENT-E2E-TERMINATION-002"
assert not Employee.search([("name", "=", name)], limit=1), "Fixture already exists"

employee = Employee.create({"name": name, "active": True})
assert not Contract.search([("employee_id", "=", employee.id)], limit=1)

start = date(2026, 10, 14)
contract = Contract.create({
    "name": "TALENT-E2E-CONTRACT-002",
    "employee_id": employee.id,
    "company_id": employee.company_id.id,
    "date_start": start,
    "wage": 1.0,
    "date_generated_from": datetime(2026, 10, 14, 0, 0),
    "date_generated_to": datetime(2026, 10, 14, 0, 0),
    "work_entry_source": "calendar",
    "x_risk_type": "1",
    "state": "draft",
})
contract.write({"state": "open"})
assert contract.state == "open" and contract.employee_id == employee
print({"synthetic_employee_id": employee.id,
       "synthetic_contract_id": contract.id,
       "contract_state": contract.state})
# Only when every assertion/validation succeeds:
env.cr.commit()
```

Record the new employee ID. If Odoo throws any exception, do not commit;
fix the staging fixture only.

## Run from GitHub Actions

Open the **Manual — Talent Termination Staging E2E** workflow on the
repository's `main` branch and select **Run workflow**.

First run with:

- `employee_id`: the new employee ID from Odoo.sh staging.
- `effective_date`: `2026-10-14` (not before the synthetic contract
  start and not a future date).
- `mode`: `dry-run`.
- `confirmation`: leave empty.

A successful dry-run reports `DRY_RUN` and `remote_writes: 0`.
Only after inspecting those results and confirming Odoo staging has no
unexpected payroll side effects, run a SECOND manual workflow:

- Same employee ID and date.
- `mode`: `execute`.
- `confirmation`: `EXECUTE-E2E-TERMINATION-<employee_id>`
  (replace placeholder with the numeric ID).

The script creates synthetic Talent objects only in its ephemeral PostgreSQL
instance. The execution must verify:

- Odoo employee archived, contract `close`, correct `date_end`.
- Cognito synthetic user `Enabled=False`, with the verified immutable `sub`.
- Talent request `COMPLETED`; checkpoints `odoo_closed_and_archived` and
  `access_disabled`; employee `DISABLED`.
- A second call of the executor returns `idempotent=True` without duplicate
  external writes. The recorder counts actual Odoo writes and Cognito disables.

If the workflow fails AFTER external writes, **do not blindly rerun**:
PostgreSQL is ephemeral, so state persisted within a failed job is lost
when the runner is destroyed. Reconcile Odoo/Cognito staging state
manually before creating any new fixture. Keep the real Talent production
feature flag OFF at all times.

## Scope

This proves an end-to-end termination for synthetic external integrations,
with checkpoints persisted and retried **within one job**. A separate
persistent Talent Staging environment is still necessary for validating
multi-day recovery, concurrent requests, user-interface authorization,
outbox orchestration, or production-grade observability.
