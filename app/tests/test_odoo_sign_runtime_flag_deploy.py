"""Ensure staging Sign flags reach the deployed API without default-on behavior.

Production deploy must not silently drop enabled features from Secrets Manager.
These checks are static and never access AWS credentials or Odoo.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SIGN_KEYS = (
    "ODOO_SIGN_STAGING_PREPARE_ENABLED",
    "ODOO_SIGN_STAGING_TRACK_ENABLED",
    "ODOO_SIGN_STAGING_SEND_ENABLED",
    "ODOO_SIGN_STAGING_ARCHIVE_ENABLED",
    "ODOO_SIGN_STAGING_SIGNED_ATTACHMENT_FIELD",
    "ODOO_SIGN_TEST_EMPLOYEE_IDS",
    "ODOO_SIGN_TEST_SIGNER_EMAILS",
    "ADN360_REQUIRE_SIGNED_CONTRACT_FOR_HIRE",
)

FLAG_KEYS = (
    "ODOO_SIGN_STAGING_PREPARE_ENABLED",
    "ODOO_SIGN_STAGING_TRACK_ENABLED",
    "ODOO_SIGN_STAGING_SEND_ENABLED",
    "ODOO_SIGN_STAGING_ARCHIVE_ENABLED",
    "ADN360_REQUIRE_SIGNED_CONTRACT_FOR_HIRE",
)


def test_runtime_secret_keys_are_forwarded_to_lightsail():
    workflow = (ROOT / ".github/workflows/deploy.yml").read_text()
    secret_load = workflow.split("for OPTIONAL_KEY in ", 1)[1].split("; do", 1)[0]
    to_deploy = workflow.split("sudo -H -E /tmp/ai-recruiter-deploy-api.sh")[0].splitlines()[-1]
    for key in SIGN_KEYS:
        assert key in secret_load, f"{key} must load from runtime secret"
        assert f'{key}="${key}"' in to_deploy, f"{key} must reach deploy-api.sh"


def test_api_container_receives_flags_with_fail_closed_defaults():
    script = (ROOT / "scripts/deploy-api.sh").read_text()
    defaults = script.split("run_api() {", 1)[0]
    docker_envs = script.split("run_api() {", 1)[1].split("local container_env", 1)[0]
    verification = script.split("local container_env", 1)[1]
    for key in SIGN_KEYS:
        assert f'-e "{key}=${key}"' in docker_envs
        assert f'"{key}=${key}"' in verification
    for key in FLAG_KEYS:
        assert f'{key}="${{{key}:-false}}"' in defaults
