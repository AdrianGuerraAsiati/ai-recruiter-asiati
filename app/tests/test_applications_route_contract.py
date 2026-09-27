"""Contract coverage for the global applications view."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_applications_route_is_specific_and_permission_protected():
    text = (
        ROOT / "app" / "domains" / "candidates" / "router.py"
    ).read_text(encoding="utf-8")

    specific = text.index('@router.get("/applications")')
    dynamic = text.index('@router.get("/{candidate_id}")')

    assert specific < dynamic
    route_source = text[specific:dynamic]
    assert 'Depends(require_permission("candidates.read"))' in route_source
    assert "service.list_applications_page" in route_source


def test_applications_repository_is_owner_scoped():
    text = (
        ROOT / "app" / "domains" / "candidates" / "repository.py"
    ).read_text(encoding="utf-8")

    start = text.index("def list_applications_page")
    end = text.index("\n\ndef count_candidates", start)
    source = text[start:end]

    assert "Candidate.owner_sub == owner_sub" in source
    assert "Job.owner_sub == owner_sub" in source
