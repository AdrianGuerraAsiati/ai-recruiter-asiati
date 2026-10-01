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
