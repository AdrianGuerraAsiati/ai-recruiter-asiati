from __future__ import annotations

import asyncio
import concurrent.futures
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

from .browser_use_driver import (
    _load_browser_session_class,
    _resolve_browser_executable,
    _runtime_value,
)
from .config import AgentConfig

_COMPUTRABAJO_PORTAL = "https://co.computrabajo.com/"
_ALLOWED_HOST_SUFFIXES = ("computrabajo.com", "computrabajo.com.co")


def safe_computrabajo_url(raw_url: str | None = None) -> str:
    value = str(raw_url or _COMPUTRABAJO_PORTAL).strip()
    parsed = urlparse(value)
    host = str(parsed.hostname or "").casefold()
    if parsed.scheme != "https" or not host:
        raise ValueError("COMPUTRABAJO_UNSAFE_URL")
    if not any(
        host == suffix or host.endswith(f".{suffix}")
        for suffix in _ALLOWED_HOST_SUFFIXES
    ):
        raise ValueError("COMPUTRABAJO_UNSAFE_URL")
    return value


class ComputrabajoBrowserUse:
    """Visible persistent Browser Use session dedicated to Computrabajo.

    This runtime intentionally contains no Indeed selectors. It is the isolated
    foundation for the Computrabajo vacancy/candidate collectors so changes in
    either website do not contaminate the other provider.
    """

    def __init__(
        self,
        config: AgentConfig,
        *,
        browser_session_class=None,
        browser_executable_resolver=None,
    ) -> None:
        self._config = config
        self._browser_name = str(
            config.browser_name or "chrome"
        ).strip().casefold()
        if self._browser_name == "chrome":
            self._browser_label = "Google Chrome"
        elif self._browser_name == "edge":
            self._browser_label = "Microsoft Edge"
        else:
            raise ValueError(f"Navegador no soportado: {self._browser_name}")

        self._profile_dir = (
            Path(config.browser_profile_dir).parent
            / f"browser-profile-{self._browser_name}-computrabajo"
        )
        self._browser_session_class = browser_session_class
        self._browser_executable_resolver = (
            browser_executable_resolver
            or (lambda: _resolve_browser_executable(self._browser_name))
        )
        self._browser = None
        self._closed = False
        self._loop = asyncio.new_event_loop()
        self._loop_ready = threading.Event()
        self._loop_thread = threading.Thread(
            target=self._run_loop,
            name="asiati-computrabajo-browser-use",
            daemon=True,
        )
        self._loop_thread.start()
        self._loop_ready.wait(timeout=5.0)

    @property
    def browser_label(self) -> str:
        return self._browser_label

    @property
    def profile_dir(self) -> Path:
        return self._profile_dir

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop_ready.set()
        self._loop.run_forever()
        pending = asyncio.all_tasks(self._loop)
        for task in pending:
            task.cancel()
        if pending:
            self._loop.run_until_complete(
                asyncio.gather(*pending, return_exceptions=True)
            )
        self._loop.close()

    def _call(self, coro, *, timeout: float | None = None):
        if self._closed:
            raise RuntimeError("COMPUTRABAJO_BROWSER_CLOSED")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        resolved_timeout = timeout or max(
            60.0,
            float(self._config.request_timeout_seconds) * 4.0,
        )
        try:
            return future.result(timeout=resolved_timeout)
        except concurrent.futures.TimeoutError as exc:
            future.cancel()
            raise TimeoutError("COMPUTRABAJO_BROWSER_TIMEOUT") from exc

    async def _ensure_started_once(self):
        if self._browser is None:
            session_class = (
                self._browser_session_class or _load_browser_session_class()
            )
            self._profile_dir.mkdir(parents=True, exist_ok=True)
            executable = self._browser_executable_resolver()
            self._browser = session_class(
                executable_path=executable,
                user_data_dir=str(self._profile_dir.resolve()),
                headless=False,
                allowed_domains=[
                    "computrabajo.com",
                    "*.computrabajo.com",
                    "computrabajo.com.co",
                    "*.computrabajo.com.co",
                    "accounts.google.com",
                ],
                accept_downloads=True,
                auto_download_pdfs=False,
                enable_default_extensions=False,
                captcha_solver=False,
                chromium_sandbox=True,
                highlight_elements=False,
                dom_highlight_elements=False,
            )
            await self._browser.start()

        cdp = await self._browser.get_or_create_cdp_session(
            self._browser.agent_focus_target_id,
            focus=True,
        )
        await cdp.cdp_client.send.Page.enable(session_id=cdp.session_id)
        await cdp.cdp_client.send.Runtime.enable(session_id=cdp.session_id)
        return cdp

    async def _ensure_started(self):
        try:
            return await self._ensure_started_once()
        except Exception:
            if self._browser is None:
                raise
            await self._discard_browser_session()
            return await self._ensure_started_once()

    async def _discard_browser_session(self) -> None:
        browser = self._browser
        self._browser = None
        if browser is not None:
            try:
                await browser.stop()
            except Exception:
                pass

    async def _evaluate(self, cdp, expression: str):
        result = await cdp.cdp_client.send.Runtime.evaluate(
            params={
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
            },
            session_id=cdp.session_id,
        )
        return _runtime_value(result)

    async def _wait_ready(self, cdp) -> None:
        deadline = time.monotonic() + max(
            8.0,
            float(self._config.request_timeout_seconds),
        )
        while time.monotonic() < deadline:
            state = await self._evaluate(cdp, "document.readyState")
            if state in {"interactive", "complete"}:
                await asyncio.sleep(0.35)
                return
            await asyncio.sleep(0.25)
        raise TimeoutError("COMPUTRABAJO_NAVIGATION_TIMEOUT")

    async def _open_portal(self, url: str | None = None) -> None:
        cdp = await self._ensure_started()
        safe_url = safe_computrabajo_url(url)
        await cdp.cdp_client.send.Page.navigate(
            params={"url": safe_url},
            session_id=cdp.session_id,
        )
        await self._wait_ready(cdp)

    def open_portal(self, url: str | None = None) -> None:
        self._call(self._open_portal(url))

    def start(self) -> None:
        self._call(self._ensure_started())

    def close(self) -> None:
        if self._closed:
            return
        try:
            self._call(self._discard_browser_session(), timeout=30.0)
        except Exception:
            pass
        self._closed = True
        try:
            self._loop.call_soon_threadsafe(self._loop.stop)
        except Exception:
            return
        self._loop_thread.join(timeout=5.0)
