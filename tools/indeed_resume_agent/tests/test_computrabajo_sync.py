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


def test_all_candidates_only_and_resume_checkpoint(tmp_path):
    from tools.indeed_resume_agent.computrabajo_sync import sync_all_candidates

    browser = Mock()
    browser.discover_all_candidates.return_value = {
        "candidates": [fake_candidate(1), fake_candidate(2)],
        "pages": 3, "partial": False, "cancelled": False,
    }
    browser.collect_candidate.return_value = {
        "name": "Sample", "filename": "cv.pdf",
        "data": b"%PDF-test", "content_type": "application/pdf",
    }
    api = Mock()
    api.ingest_source_candidate.return_value = {"existing": False, "queued": True}
    path = tmp_path / "state.json"
    first = sync_all_candidates(
        browser=browser, api=api, source_account="ASIATI", checkpoint_path=path,
    )
    assert first["created"] == 2
    assert first["pages"] == 3
    assert api.ingest_source_candidate.call_count == 2
    for invocation in api.ingest_source_candidate.call_args_list:
        assert not invocation.kwargs.get("job_title")
        assert "external_job_id" not in invocation.kwargs
    checkpoint = path.read_text(encoding="utf-8")
    assert '"external_id"' not in checkpoint
    assert '"1"' not in checkpoint
    second = sync_all_candidates(
        browser=browser, api=api, source_account="ASIATI", checkpoint_path=path,
    )
    assert second["skipped"] == 2
    assert api.ingest_source_candidate.call_count == 2


def test_failed_submission_is_retryable(tmp_path):
    from tools.indeed_resume_agent.computrabajo_sync import sync_all_candidates

    browser = Mock()
    browser.discover_all_candidates.return_value = {
        "candidates": [fake_candidate(1)],
        "pages": 1, "partial": True, "cancelled": False,
    }
    browser.collect_candidate.return_value = {
        "name": "Sample", "filename": "cv.pdf",
        "data": b"%PDF-test", "content_type": "application/pdf",
    }
    api = Mock()
    api.ingest_source_candidate.side_effect = [
        {"existing": False, "queued": False},
        {"existing": False, "queued": True},
    ]
    path = tmp_path / "progress.json"
    first = sync_all_candidates(browser=browser, api=api,
                                source_account="asiati", checkpoint_path=path)
    assert first["failed"] == 1 and first["partial"] is True
    second = sync_all_candidates(browser=browser, api=api,
                                 source_account="asiati", checkpoint_path=path)
    assert second["created"] == 1
    assert api.ingest_source_candidate.call_count == 2


def test_sync_all_stop_does_not_visit_candidates(tmp_path):
    from tools.indeed_resume_agent.computrabajo_sync import sync_all_candidates
    browser = Mock()
    browser.discover_all_candidates.return_value = {
        "candidates": [fake_candidate(1)],
        "pages": 1, "partial": False, "cancelled": True,
    }
    result = sync_all_candidates(browser=browser, api=Mock(),
                                 source_account="asiati", checkpoint_path=tmp_path / "cp.json",
                                 stop_requested=lambda: True)
    assert result["cancelled"] is True
    browser.collect_candidate.assert_not_called()


def test_sync_reports_pdf_and_api_failures_separately(tmp_path):
    from tools.indeed_resume_agent.computrabajo_sync import sync_all_candidates
    from tools.indeed_resume_agent.api_client import AgentApiError

    browser = Mock()
    browser.discover_all_candidates.return_value = {
        "candidates": [fake_candidate(1), fake_candidate(2)],
        "pages": 2, "blocked_pages": 1, "partial": True, "cancelled": False,
    }
    browser.collect_candidate.side_effect = [
        RuntimeError("COMPUTRABAJO_OFFER_EXPIRED_ACCESS_DENIED"),
        {"name": "Second", "filename": "cv.pdf", "data": b"%PDF-1.7",
         "content_type": "application/pdf"},
    ]
    api = Mock()
    api.ingest_source_candidate.side_effect = AgentApiError(422, "HTTP_422")
    outcome = sync_all_candidates(
        browser=browser, api=api, source_account="ASIATI",
        checkpoint_path=tmp_path / "checkpoint.json",
    )
    assert outcome["created"] == 0 and outcome["failed"] == 2
    assert outcome["blocked_pages"] == 1
    assert outcome["error_counts"] == {
        "descarga:COMPUTRABAJO_OFFER_EXPIRED_ACCESS_DENIED": 1,
        "talent:HTTP_422": 1,
    }
    assert api.ingest_source_candidate.call_count == 1
