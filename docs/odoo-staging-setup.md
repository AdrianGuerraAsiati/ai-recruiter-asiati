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

No staging key, staging deployment, or Odoo test data is created by this PR. Contract-termination E2E remains blocked until staging access is independently verified.
