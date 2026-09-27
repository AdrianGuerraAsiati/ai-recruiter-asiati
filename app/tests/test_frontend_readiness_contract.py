"""Regression contract for frontend rollback/readiness during production deploy."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "deploy.yml"
FRONTEND_SCRIPT = ROOT / "scripts" / "deploy-frontend.sh"


def test_frontend_deploy_uses_versioned_rollback_script():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    script = FRONTEND_SCRIPT.read_text(encoding="utf-8")

    assert "scripts/deploy-frontend.sh" in workflow
    assert "FRONTEND_ROLLBACK_OK" in script
    assert "OLD_IMAGE" in script

    pull = script.index('docker pull "$IMAGE"')
    replace = script.index('docker rm -f "$CONTAINER_NAME"')
    assert pull < replace


def test_frontend_local_readiness_is_retried_before_success():
    script = FRONTEND_SCRIPT.read_text(encoding="utf-8")

    assert "for _ in $(seq 1 15); do" in script
    assert "curl -fS http://127.0.0.1/" in script
    assert "id=\"root\"" in script
    assert "verify_frontend" in script
