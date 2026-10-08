import asyncio
import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from tools.indeed_resume_agent.computrabajo_browser import ComputrabajoBrowserUse

DETAIL = "https://empresa.co.computrabajo.com/Company/MatchCvDetail/MatchDetail?oi=0123&ims=4567"


def fake_browser(meta, fetch_result=None):
    browser = object.__new__(ComputrabajoBrowserUse)
    page = SimpleNamespace(
        navigate=AsyncMock(),
        printToPDF=AsyncMock(return_value={
            "data": base64.b64encode(b"%PDF-1.7\\nprofile").decode()
        }),
    )
    cdp = SimpleNamespace(cdp_client=SimpleNamespace(send=SimpleNamespace(Page=page)),
                          session_id="session")
    browser._ensure_started = AsyncMock(return_value=cdp)
    browser._wait_ready = AsyncMock()
    browser._evaluate = AsyncMock(side_effect=[meta] + ([fetch_result] if fetch_result else []))
    return browser, page


def test_attachment_preferred_over_generated_profile_pdf():
    browser, page = fake_browser(
        {"attachment_url": "https://empresa.co.computrabajo.com/Company/CvDownloader/Company/CvDetail/Download?ims=4567", "name": "Sample"},
        {"content": base64.b64encode(b"%PDF-1.7\\nattached").decode(), "type": "application/pdf"},
    )
    result = asyncio.run(browser._collect_candidate_async({"detail_url": DETAIL, "candidate_name": "Example"}))
    assert result["kind"] == "attached"
    assert result["data"].startswith(b"%PDF-")
    page.printToPDF.assert_not_awaited()


def test_missing_attachment_uses_profile_pdf():
    browser, page = fake_browser({"attachment_url": "", "name": "Sample"})
    result = asyncio.run(browser._collect_candidate_async({"detail_url": DETAIL, "candidate_name": "Example"}))
    assert result["kind"] == "profile"
    page.printToPDF.assert_awaited_once()


def test_external_candidate_urls_rejected_before_navigation():
    browser, page = fake_browser({"attachment_url": ""})
    with pytest.raises(ValueError, match="COMPUTRABAJO_INVALID_CANDIDATE_URL"):
        asyncio.run(browser._collect_candidate_async({
            "detail_url": "https://attacker.invalid/Company/MatchCvDetail/MatchDetail"}))
    page.navigate.assert_not_awaited()
