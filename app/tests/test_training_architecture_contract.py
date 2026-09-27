"""Architecture contracts for the training domain split."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "app" / "domains" / "training" / "service.py"
PRESET = ROOT / "app" / "domains" / "training" / "asiati_preset.py"


def test_training_service_keeps_asiati_preset_out_of_generic_service():
    service = SERVICE.read_text(encoding="utf-8")
    preset = PRESET.read_text(encoding="utf-8")

    assert len(service.splitlines()) < 1600
    assert "ASIATI_ONBOARDING_MODULE_1_TITLE" not in service
    assert "create_asiati_onboarding_template" in service
    assert "ensure_published_asiati_onboarding" in service

    assert "ASIATI_ONBOARDING_MODULE_1_TITLE" in preset
    assert "def create_asiati_onboarding_template(" in preset
    assert "def ensure_published_asiati_onboarding(" in preset


def test_training_page_is_split_into_feature_modules():
    page = (
        ROOT / "frontend-react" / "src" / "pages" / "Training.jsx"
    ).read_text(encoding="utf-8")

    assert len(page.splitlines()) < 2000
    assert "../features/training/trainingUtils" in page
    assert "../features/training/TrainingAdminPanels" in page



def test_training_models_live_in_domain_with_compatibility_facade():
    facade_path = ROOT / "app" / "models.py"
    domain_path = ROOT / "app" / "domains" / "training" / "models.py"
    facade = facade_path.read_text(encoding="utf-8")
    domain = domain_path.read_text(encoding="utf-8")

    assert len(facade.splitlines()) < 900
    assert "class TrainingCourse(Base):" not in facade
    assert "from app.domains.training.models import" in facade

    assert "class TrainingCourse(Base):" in domain
    assert "class TrainingQuizAttempt(Base):" in domain
