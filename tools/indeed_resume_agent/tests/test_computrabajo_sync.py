from unittest.mock import Mock
import pytest
from tools.indeed_resume_agent.computrabajo_sync import sync_visible_candidates


def fake_candidate(n):
    return {"external_id": str(n), "external_job_id": "job", "detail_url": "https://example.invalid"}


def test_sync_reports_new_existing_and_failed_per_candidate():
    browser = Mock()
    browser.discover_visible_candidates.return_value = [fake_candidate(1), fake_candidate(2), fake_candidate(3)]
    browser.collect_candidate.side_effect = [
        {"name": "First", "filename": "cv.pdf", "data": b"%PDF-a", "content_type": "application/pdf"},
        {"name": "Second", "filename": "cv.pdf", "data": b"%PDF-b", "content_type": "application/pdf"},
        RuntimeError("provider unavailable"),
    ]
    api = Mock()
    api.ingest_source_candidate.side_effect = [
        {"existing": False}, {"existing": True}
    ]
    reports = []
    result = sync_visible_candidates(browser=browser, api=api,
        source_account="asiati", job_title="Developer", progress=lambda i,r: reports.append((i,r)))
    assert (result["created"], result["existing"], result["failed"]) == (1,1,1)
    assert len(reports) == 3
    assert api.ingest_source_candidate.call_args.kwargs["provider"] == "COMPUTRABAJO"
    assert api.ingest_source_candidate.call_count == 2


def test_sync_can_stop_before_next_candidate():
    browser = Mock()
    browser.discover_visible_candidates.return_value = [fake_candidate(1)]
    result = sync_visible_candidates(browser=browser, api=Mock(),
        source_account="asiati", job_title="Developer", stop_requested=lambda: True)
    assert result["cancelled"] is True
    browser.collect_candidate.assert_not_called()


def test_sync_requires_context():
    with pytest.raises(ValueError, match="COMPUTRABAJO_CONTEXT_REQUIRED"):
        sync_visible_candidates(browser=Mock(), api=Mock(),
            source_account="", job_title="Developer")
