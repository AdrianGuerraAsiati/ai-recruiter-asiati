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
