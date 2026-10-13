import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from tools.indeed_resume_agent.computrabajo_browser import ComputrabajoBrowserUse

DETAIL = "https://empresa.co.computrabajo.com/Company/MatchCvDetail/MatchDetail?oi=0123&ims=4567"


def fake_browser(profile):
    browser = object.__new__(ComputrabajoBrowserUse)
    page = MagicMock()
    page.navigate = AsyncMock()
    cdp = MagicMock()
    cdp.cdp_client.send.Page = page
    cdp.session_id = "test"
    browser._ensure_started = AsyncMock(return_value=cdp)
    browser._wait_ready = AsyncMock()
    browser._evaluate = AsyncMock(return_value=profile)
    return browser, page


def test_read_profile_name_without_downloading_cv():
    browser, page = fake_browser({"name": "María Fernanda Torres"})
    result = asyncio.run(browser._read_candidate_profile_name_async(DETAIL))
    assert result == "María Fernanda Torres"
    page.navigate.assert_awaited_once()
    page.printToPDF.assert_not_called()


def test_rejects_vacancy_heading():
    browser, page = fake_browser({"name": "Oferta Director financiero - Latam"})
    with pytest.raises(RuntimeError, match="COMPUTRABAJO_NAME_UNVERIFIED"):
        asyncio.run(browser._read_candidate_profile_name_async(DETAIL))


def test_rejects_foreign_profile_url_without_navigation():
    browser, page = fake_browser({"name": "María Fernanda Torres"})
    with pytest.raises(ValueError, match="COMPUTRABAJO_INVALID_CANDIDATE_URL"):
        asyncio.run(browser._read_candidate_profile_name_async("https://example.com/profile"))
    page.navigate.assert_not_awaited()
