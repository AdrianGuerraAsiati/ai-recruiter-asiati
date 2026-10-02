"""Regression contract for Docker disk cleanup before production image pulls."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_production_preflight_reclaims_old_deploy_images_before_pull():
    workflow = (ROOT / ".github/workflows/deploy.yml").read_text(encoding="utf-8")

    migrate = workflow.index("- name: Migrate and backfill production database")
    deploy = workflow.index("- name: Deploy API worker and frontend via SSH", migrate)
    preflight = workflow[migrate:deploy]

    assert "docker container prune -f" in preflight
    assert "prune_old_repo_images()" in preflight
    assert 'repo="\\$1"' in preflight
    assert 'keep="\\${2:-3}"' in preflight
    assert 'docker image ls "\\$repo"' in preflight
    assert '"\\${#images[@]}"' in preflight
    assert '"\\${images[@]:\\$keep}"' in preflight
    assert 'prune_old_repo_images "$ECR_REGISTRY/$ECR_BACKEND_REPO" 3' in preflight
    assert 'prune_old_repo_images "$ECR_REGISTRY/$ECR_FRONTEND_REPO" 3' in preflight
    assert "docker image prune -f" in preflight
    assert "docker builder prune -a -f" in preflight
    assert "docker system df" in preflight
    assert "--volumes" not in preflight


def test_production_preflight_does_not_use_unescaped_awk_in_remote_heredoc():
    workflow = (ROOT / ".github/workflows/deploy.yml").read_text(encoding="utf-8")

    migrate = workflow.index("- name: Migrate and backfill production database")
    deploy = workflow.index("- name: Deploy API worker and frontend via SSH", migrate)
    preflight = workflow[migrate:deploy]

    assert "awk '$0" not in preflight
    assert "--filter dangling=false" in preflight


def test_production_reclaims_disk_before_roles_anywhere_identity_check():
    workflow = (ROOT / ".github/workflows/deploy.yml").read_text(encoding="utf-8")

    cleanup = workflow.index("- name: Reclaim Docker disk before identity check")
    identity = workflow.index("- name: Verify existing Roles Anywhere identity")

    assert cleanup < identity
    pre_identity = workflow[cleanup:identity]
    assert "docker container prune -f" in pre_identity
    assert "docker image prune -a -f" in pre_identity
    assert "docker builder prune -a -f" in pre_identity
