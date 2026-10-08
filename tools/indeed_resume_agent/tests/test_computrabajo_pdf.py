"""Safe, manual Computrabajo CV profile PDF export."""
import asyncio
import base64
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tools.indeed_resume_agent.computrabajo_browser import ComputrabajoBrowserUse


def make_browser(tmp_path, url):
    instance = object.__new__(ComputrabajoBrowserUse)
    instance._profile_dir = tmp_path / "browser-profile-chrome-computrabajo"
    instance._ensure_started = AsyncMock(return_value=SimpleNamespace(
        cdp_client=SimpleNamespace(send=AsyncMock(return_value={
            "data": base64.b64encode(b"%PDF-1.7\nexample").decode()
        })),
        session_id="session",
    ))
    instance._page_metadata = AsyncMock(return_value={"url": url})
    return instance


def test_manual_pdf_save_only_from_candidate_page(tmp_path):
    browser = make_browser(
        tmp_path, "https://empresa.co.computrabajo.com/Company/MatchCvDetail/MatchPrint"
    )
    result = asyncio.run(browser._save_visible_profile_pdf_async())
    assert Path(result).read_bytes().startswith(b"%PDF-")
    assert Path(result).parent.name == "computrabajo"


@pytest.mark.parametrize("url", [
    "https://example.com/Company/MatchCvDetail/MatchPrint",
    "https://empresa.co.computrabajo.com/Company/Offers/Match",
    "https://empresa.co.computrabajo.com.evil.test/Company/MatchCvDetail/MatchPrint",
])
def test_manual_pdf_rejects_other_pages_without_export(tmp_path, url):
    browser = make_browser(tmp_path, url)
    with pytest.raises(ValueError, match="COMPUTRABAJO_PROFILE_REQUIRED"):
        asyncio.run(browser._save_visible_profile_pdf_async())
    assert not (tmp_path / "exports").exists()
