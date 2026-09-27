# AI Recruiter infrastructure

This directory contains only infrastructure that belongs to the current production path or current operational support.

## Current production path

Production is deployed by `.github/workflows/deploy.yml` to a Lightsail host in `us-east-2`.

The supported runtime consists of:

- `ai-recruiter-web`: Nginx + React SPA.
- `ai-recruiter-api`: FastAPI.
- `ai-recruiter-worker`: asynchronous candidate/import worker.
- PostgreSQL running on the host.
- Amazon ECR for immutable backend/frontend images.
- Amazon S3/SQS/Bedrock/Cognito/Secrets Manager integrations consumed by the runtime.

GitHub Actions authenticates to AWS through OIDC. The Lightsail host consumes AWS through IAM Roles Anywhere.

## Versioned infrastructure

### candidate-import.yml

Creates the private temporary S3 staging bucket plus the import queue and DLQ.

### training-content.yml

Creates the private persistent training-media bucket. The bucket is versioned and retained on CloudFormation replacement/deletion.

### lightsail_logs_to_cloudwatch.sh / lightsail_logs_iam_policy.json

Optional operational support for forwarding host/container logs. These files do not imply that log forwarding is active until the production host has been configured and verified.

## Deployment scripts

The production workflow copies and executes the versioned scripts under `scripts/`:

- `deploy-api.sh`
- `deploy-worker.sh`
- `deploy-frontend.sh`
- `backup-postgres.sh` before schema migrations

API and frontend deployment scripts automatically restore the previously running image if the new container fails its local readiness check. Worker deployment retains its existing image rollback path.

## Database ownership

Alembic is the only schema owner. Application startup must not create/alter tables implicitly.

Before production migrations, CI creates a restricted local PostgreSQL dump under `/opt/ai-recruiter/backups`. This protects against migration/application rollback mistakes, but it is **not** a host-loss/disaster-recovery backup.

An encrypted off-host backup/restore path remains required and must be validated against the live AWS environment before being enabled.

## Retired infrastructure

Historical ECS/ALB/CloudFront/static-S3, EC2 bootstrap, canary-routing, feature-flag and legacy OIDC artifacts were removed from `main` during the 2026-09-27 infrastructure audit. Git history remains the source for those retired implementations.

Do not copy old deployment artifacts back into `infra/` unless they are being deliberately reactivated, tested and documented as part of the supported production path.


## Observability

The API emits a correlation ID in `X-Request-ID` and logs one structured request-completion event with method, path, status and latency. Candidate-import worker deliveries use `candidate-import:<batch_id>` as their correlation scope so queue failures can be traced across retries.

`candidate-import.yml` provisions CloudWatch alarms for:

- candidate-import DLQ visible messages >= 1;
- main queue visible backlog >= 50 for two consecutive periods;
- oldest queued message >= 15 minutes for two consecutive periods.

The alarms are created even when notifications are not configured. To attach an existing SNS topic, add the optional `CANDIDATE_IMPORT_ALARM_TOPIC_ARN` key to the production runtime-config secret.

## Off-host database backup

The pre-migration backup always writes a restricted local custom-format dump plus SHA-256 checksum.

Off-host copying is opt-in. Add `DATABASE_BACKUP_S3_URI` to the production runtime-config secret only after a private backup destination and the runtime role's least-privilege write access have been reviewed. When configured, the same backup and checksum are copied with S3 server-side encryption.

Example value:

```text
s3://<private-backup-bucket>/postgres/production
```

The deploy intentionally treats an off-host copy failure as a failed pre-migration backup and stops before applying schema changes.


### Restore drill

`scripts/restore-postgres.sh` accepts either a local dump path or an `s3://` URI. Remote restores require the dump checksum object at the same URI with the `.sha256` suffix.

The script refuses destructive restore unless `CONFIRM_RESTORE=yes` is provided and always validates SHA-256 before invoking `pg_restore`.

A real disaster-recovery drill should restore into a disposable PostgreSQL target first; never validate a backup by restoring over production.
