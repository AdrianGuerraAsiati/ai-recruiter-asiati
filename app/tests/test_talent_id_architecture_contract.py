"""Architecture contracts for Talent ID inside Talent Intelligence."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_talent_id_reuses_employee_identity_instead_of_projecting_employees():
    models = (
        ROOT / "app" / "domains" / "talent_id" / "models.py"
    ).read_text(encoding="utf-8")

    assert "class UserProfile" not in models
    assert 'ForeignKey("user_profiles.id"' in models
    assert "workforce_employees" not in models


def test_talent_id_is_composed_into_main_application():
    bootstrap = (ROOT / "app" / "bootstrap.py").read_text(encoding="utf-8")

    assert "app.domains.talent_id.router" in bootstrap
    assert "talent_id_router" in bootstrap



def test_talent_id_production_deploy_injects_security_runtime_settings():
    deploy_workflow = (
        ROOT / ".github" / "workflows" / "deploy.yml"
    ).read_text(encoding="utf-8")
    deploy_script = (
        ROOT / "scripts" / "deploy-api.sh"
    ).read_text(encoding="utf-8")

    required = (
        "TALENT_ID_REKOGNITION_COLLECTION_ID",
        "TALENT_ID_CONSENT_FROM_EMAIL",
        "TALENT_ID_CONSENT_OTP_SECRET",
        "TALENT_ID_FROM_EMAIL",
        "TALENT_ID_MOBILE_LINK_OTP_SECRET",
        "TALENT_ID_QR_TOKEN_TTL_SECONDS",
    )
    for key in required:
        assert key in deploy_workflow
        assert key in deploy_script
