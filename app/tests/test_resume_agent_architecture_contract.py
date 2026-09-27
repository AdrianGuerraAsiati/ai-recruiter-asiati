"""Architecture contracts for the Indeed Resume Agent browser drivers."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BROWSER = ROOT / "tools" / "indeed_resume_agent" / "browser.py"
BROWSER_USE = ROOT / "tools" / "indeed_resume_agent" / "browser_use_driver.py"
SEARCH = ROOT / "tools" / "indeed_resume_agent" / "candidate_search.py"
DOCUMENTS = ROOT / "tools" / "indeed_resume_agent" / "documents.py"


def test_browser_drivers_share_candidate_search_helpers():
    browser = BROWSER.read_text(encoding="utf-8")
    browser_use = BROWSER_USE.read_text(encoding="utf-8")
    search = SEARCH.read_text(encoding="utf-8")

    assert "from .candidate_search import" in browser
    assert "from .candidate_search import" in browser_use
    assert "def normalize_lookup_text(" in search
    assert "def candidate_search_queries(" in search
    assert "def candidate_search_url(" in search


def test_document_validation_is_not_owned_by_browser_driver():
    browser = BROWSER.read_text(encoding="utf-8")
    browser_use = BROWSER_USE.read_text(encoding="utf-8")
    documents = DOCUMENTS.read_text(encoding="utf-8")

    assert "from .documents import" in browser
    assert "from .documents import" in browser_use
    assert "def validate_resume_document(" not in browser
    assert "def validate_resume_document(" in documents


def test_resume_agent_god_files_do_not_regrow_after_split():
    assert len(BROWSER.read_text(encoding="utf-8").splitlines()) < 2050
    assert len(BROWSER_USE.read_text(encoding="utf-8").splitlines()) < 1160
