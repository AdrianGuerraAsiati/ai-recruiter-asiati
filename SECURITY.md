# Security Policy

## Reporting a vulnerability

Do not publish credentials, candidate data, employee data, tokens, CVs, or exploit details in a public issue.

Use GitHub's private vulnerability reporting/security-advisory flow when available. If private reporting is unavailable, contact the repository maintainers through an approved private corporate channel.

Include:

- affected component and version/commit;
- reproduction steps with synthetic data only;
- expected and observed behavior;
- impact assessment;
- any suggested remediation.

## Secrets

Never commit AWS credentials, OAuth client secrets, refresh tokens, private keys, production database URLs, candidate documents, or employee documents.

If a secret is committed, treat it as compromised and rotate/revoke it; deleting it from the latest commit is not sufficient.
