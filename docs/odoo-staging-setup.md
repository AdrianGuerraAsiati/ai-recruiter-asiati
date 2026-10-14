# Odoo staging — isolated XML-RPC credentials

This connection is intentionally independent of the production Odoo integration.

## In Odoo staging
1. Open the **staging** Odoo database (never the production database).
2. Create or choose a dedicated technical user with least-privilege access to `hr.employee` and `hr.contract`.
3. Generate an API key **inside that staging account**. Do not copy the production key.
4. Confirm the exact staging database name and `https://` hostname. An Odoo shell `env.cr.dbname` may be used for the database name.

## Talent environment variables

```dotenv
ODOO_STAGING_BASE_URL=https://asiati-test160526-39554181.dev.odoo.com
ODOO_STAGING_DATABASE=asiati-test160526-39554181
ODOO_STAGING_USERNAME=sistemas@asiati.com.co
ODOO_STAGING_SECRET_ID=/ai-recruiter/staging/odoo
```

In the **Talent AWS account**, in `us-east-2`, create the staging secret with JSON structure:

```json
{"api_key": "STAGING_API_KEY_FROM_ODOO"}
```

Never commit the key to GitHub or send it in a chat message. Restrict Secrets Manager permissions to the staging runtime identity.

The `build_staging_client()` helper refuses missing settings and rejects the production host, database, and secret. It does **not** fall back to `/ai-recruiter/prod/odoo`.

## Smoke test (read only)

Call `build_staging_client().healthcheck()` from an authorized staging runtime, then `fields_get("hr.contract")`. Compare available `state` values and ensure the staging database contains only approved test data before mutating it.

**Verified 2026-10-14:** AWS account `890876258895` and Secrets Manager secret exist in `us-east-2`. An actual independent XML-RPC call from AWS CloudShell succeeded: server `18.0+e`, authenticated UID `97`, `fields_get` on `hr.employee` and `hr.contract`; `hr.contract.state` supports `draft`, `open`, `close`, `cancel`, and `date_end` is writable. The staging user has Odoo read/write ACL on both models. This is not proof that the Talent process has these environment variables, nor an E2E write test.

## Deployment gate

1. Configure the four `ODOO_STAGING_*` variables above **only in an approved Talent staging runtime** (do not turn on termination execution in production).
2. The role used by the Talent runtime `AiRecruiterBedrockRuntimeRole` received `secretsmanager:GetSecretValue` for the **exact staging secret ARN**. Confirm the runtime actually assumes that role.
3. Deploy the approved PR and call `GET /api/odoo/staging/diagnostics` using an authenticated administrator with `employees.update` permission; expect `health.connected=true`, `uid=97`, `contract.has_state=true`, `contract.has_date_end=true`, `state_selections` including `close`, and `employee.has_active=true`.
4. For write E2E, use a **new uniquely named synthetic employee and contract** in the neutralized Odoo staging database only. Capture their record IDs, pre-state, and approvals. Do not reuse a production-synced employee. Disable all external notifications/automations for the synthetic record. Record verification and cleanup, including idempotent retry. Keep `EMPLOYEE_TERMINATION_EXECUTION_ENABLED=false` in production.

**Outstanding:** no verified Talent staging runtime or E2E contract write yet. The SQL outbox migration and PR #281 must be reviewed before any live termination flow.
