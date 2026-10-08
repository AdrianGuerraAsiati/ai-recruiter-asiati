"""Logout must clear the dedicated Computrabajo profile and close its browser."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest

from tools.indeed_resume_agent.computrabajo_browser import ComputrabajoBrowserUse


def test_logout_clears_cookies_and_storage():
    browser = object.__new__(ComputrabajoBrowserUse)
    browser._browser = object()
    send = SimpleNamespace(
        Network=SimpleNamespace(clearBrowserCookies=AsyncMock()),
        Storage=SimpleNamespace(clearDataForOrigin=AsyncMock()),
    )
    browser._ensure_started = AsyncMock(return_value=SimpleNamespace(
        cdp_client=SimpleNamespace(send=send),
        session_id="test",
    ))
    browser._discard_browser_session = AsyncMock()
    asyncio.run(browser._logout_async())
    send.Network.clearBrowserCookies.assert_awaited_once()
    assert send.Storage.clearDataForOrigin.await_count == 4
    browser._discard_browser_session.assert_awaited_once()


def test_logout_always_closes_browser_after_storage_error():
    browser = object.__new__(ComputrabajoBrowserUse)
    browser._browser = object()
    send = SimpleNamespace(Network=SimpleNamespace(
        clearBrowserCookies=AsyncMock(side_effect=RuntimeError("blocked"))
    ))
    browser._ensure_started = AsyncMock(return_value=SimpleNamespace(
        cdp_client=SimpleNamespace(send=send), session_id="test",
    ))
    browser._discard_browser_session = AsyncMock()
    with pytest.raises(RuntimeError, match="blocked"):
        asyncio.run(browser._logout_async())
    browser._discard_browser_session.assert_awaited_once()
