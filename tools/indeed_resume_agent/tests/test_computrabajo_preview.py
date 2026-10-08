"""Read-only Computrabajo screen classification contracts."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from tools.indeed_resume_agent.computrabajo_browser import ComputrabajoBrowserUse


def test_inspect_page_returns_only_aggregate_counts():
    browser = object.__new__(ComputrabajoBrowserUse)
    browser._ensure_started = AsyncMock(return_value=SimpleNamespace())
    browser._evaluate = AsyncMock(return_value={
        "page": "candidate_list",
        "candidate_links": 30,
        "vacancy_links": 0,
        "cv_download_links": 0,
        "has_filters": True,
        "title": "Gestión de candidatos",
    })
    result = asyncio.run(browser._inspect_current_page_async())
    assert result["candidate_links"] == 30
    assert result["page"] == "candidate_list"
    assert "candidate_name" not in result
    assert "email" not in result
    expression = browser._evaluate.call_args.args[1]
    assert 'a[href*="/MatchCvDetail/MatchDetail"]' in expression
    assert 'a.js_download_file[href*="/CvDownloader/"]' in expression


def test_inspect_page_fails_closed_if_dom_output_is_invalid():
    browser = object.__new__(ComputrabajoBrowserUse)
    browser._ensure_started = AsyncMock(return_value=SimpleNamespace())
    browser._evaluate = AsyncMock(return_value=None)
    try:
        asyncio.run(browser._inspect_current_page_async())
        assert False, "Expected page inspection to fail closed"
    except RuntimeError as exc:
        assert "COMPUTRABAJO_PAGE_INSPECTION_FAILED" in str(exc)
