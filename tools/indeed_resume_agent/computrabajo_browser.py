from __future__ import annotations

import asyncio
import base64
import concurrent.futures
import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urlsplit, urlunsplit

from .browser_use_driver import (
    _load_browser_session_class,
    _resolve_browser_executable,
    _runtime_value,
)
from .config import AgentConfig

_COMPUTRABAJO_PORTAL = "https://empresa.co.computrabajo.com/"
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
        self._network_registered = False
        self._diagnostic_active = False
        self._diagnostic_events: list[dict] = []
        self._diagnostic_started_at: str | None = None
        self._last_diagnostic_path: str | None = None
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

    @property
    def diagnostic_active(self) -> bool:
        return self._diagnostic_active

    @property
    def last_diagnostic_path(self) -> str | None:
        return self._last_diagnostic_path

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
        await cdp.cdp_client.send.Network.enable(session_id=cdp.session_id)
        if not self._network_registered:
            self._browser.cdp_client.register.Network.responseReceived(
                self._on_response_received
            )
            self._network_registered = True
        return cdp

    async def _ensure_started(self):
        try:
            return await self._ensure_started_once()
        except Exception:
            if self._browser is None:
                raise
            await self._discard_browser_session()
            return await self._ensure_started_once()

    async def _logout_async(self) -> None:
        """Forget credentials in Computrabajo's isolated browser profile.

        Local logout does not revoke sessions on the provider's servers.
        """
        if self._browser is None:
            return
        cdp = await self._ensure_started()
        origins = (
            "https://empresa.co.computrabajo.com",
            "https://co.computrabajo.com",
            "https://secure.computrabajo.com",
            "https://candidato.co.computrabajo.com",
        )
        try:
            await cdp.cdp_client.send.Network.clearBrowserCookies(
                session_id=cdp.session_id
            )
            for origin in origins:
                await cdp.cdp_client.send.Storage.clearDataForOrigin(
                    params={"origin": origin, "storageTypes": "all"},
                    session_id=cdp.session_id,
                )
        finally:
            await self._discard_browser_session()

    def logout(self) -> None:
        self._call(self._logout_async(), timeout=45.0)

    async def _discard_browser_session(self) -> None:
        browser = self._browser
        self._browser = None
        self._network_registered = False
        if browser is not None:
            try:
                await browser.stop()
            except Exception:
                pass

    def _record_diagnostic_event(self, payload: dict) -> None:
        if not self._diagnostic_active:
            return
        event = dict(payload)
        event["captured_at_utc"] = datetime.now(timezone.utc).isoformat()
        self._diagnostic_events.append(event)
        if len(self._diagnostic_events) > 600:
            del self._diagnostic_events[:-600]

    @staticmethod
    def _safe_diagnostic_url(raw_url: object) -> str:
        try:
            parsed = urlsplit(str(raw_url or ""))
        except Exception:
            return ""
        host = str(parsed.hostname or "").casefold()
        if not any(
            host == suffix or host.endswith(f".{suffix}")
            for suffix in _ALLOWED_HOST_SUFFIXES
        ):
            return ""
        return urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, "", "")
        )

    def _on_response_received(self, params, _session_id) -> None:
        if not self._diagnostic_active:
            return
        try:
            response = (
                params.get("response", {}) if hasattr(params, "get") else {}
            )
            url = str(response.get("url") or "")
            safe_url = self._safe_diagnostic_url(url)
            if not safe_url:
                return
            headers = response.get("headers") or {}
            content_type = ""
            if isinstance(headers, dict):
                content_type = str(
                    next(
                        (
                            value
                            for key, value in headers.items()
                            if str(key).casefold() == "content-type"
                        ),
                        "",
                    )
                )
            if not content_type:
                content_type = str(response.get("mimeType") or "")
            self._record_diagnostic_event(
                {
                    "kind": "response",
                    "status": int(response.get("status") or 0),
                    "url": safe_url,
                    "content_type": content_type.split(";", 1)[0][:160],
                }
            )
        except Exception:
            return

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

    async def _inspect_current_page_async(self) -> dict:
        """Read-only inventory of the authenticated page; never extract PII."""
        cdp = await self._ensure_started()
        payload = await self._evaluate(
            cdp,
            """(() => {
              const path = location.pathname.toLowerCase();
              const has = (selector) => document.querySelectorAll(selector).length;
              const home = /\\/company\\/(default|home|inicio)?$/.test(path);
              const listing = path.includes('/offers/match');
              const detail = path.includes('/matchcvdetail/matchdetail');
              const offers = path.includes('/company/offers') && !listing;
              return {
                page: detail ? 'candidate_detail' : listing ? 'candidate_list' :
                      offers ? 'vacancies' : home ? 'home' : 'other',
                candidate_links: has('a[href*="/MatchCvDetail/MatchDetail"]'),
                vacancy_links: has('a[href*="/Offers/Match?"]'),
                cv_download_links: has('a.js_download_file[href*="/CvDownloader/"]'),
                has_filters: !!document.querySelector('[name="MultifiltersDataModel.SearchName"]'),
                inspected: true
              };
            })()""",
        )
        if not isinstance(payload, dict):
            raise RuntimeError("COMPUTRABAJO_PAGE_INSPECTION_FAILED")
        return payload

    def inspect_current_page(self) -> dict:
        return self._call(self._inspect_current_page_async(), timeout=30.0)

    def open_vacancies(self) -> None:
        self.open_portal("https://empresa.co.computrabajo.com/Company/Offers")

    async def _discover_visible_candidates_async(self) -> list[dict]:
        """Read candidate links on the currently open employer listing page.

        Does not navigate, bypass pagination, or send candidates anywhere.
        """
        cdp = await self._ensure_started()
        data = await self._evaluate(cdp, """(() => {
            if (location.hostname !== 'empresa.co.computrabajo.com' ||
                !location.pathname.toLowerCase().includes('/company/offers/match')) {
                return {error: 'COMPUTRABAJO_LIST_REQUIRED'};
            }
            const seen = new Set();
            return [...document.querySelectorAll('a.js-o-link.nom[href*="/MatchCvDetail/MatchDetail"]')]
                .slice(0, 100)
                .map(a => {
                    const url = new URL(a.href);
                    const id = url.searchParams.get('ims') || '';
                    const job = url.searchParams.get('oi') || '';
                    if (!/^[A-Fa-f0-9]{16,64}$/.test(id) ||
                        !/^[A-Fa-f0-9]{16,64}$/.test(job) || seen.has(id)) {
                        return null;
                    }
                    seen.add(id);
                    const name = (a.querySelector('strong, b, h3, h4')?.textContent ||
                        a.textContent || '').split('\\n')[0].trim().slice(0, 180);
                    return {external_id: id, external_job_id: job,
                            candidate_name: name, detail_url: url.href};
                }).filter(Boolean);
        })()""")
        if isinstance(data, dict) and data.get("error"):
            raise ValueError(data["error"])
        if not isinstance(data, list):
            raise RuntimeError("COMPUTRABAJO_CANDIDATES_INVALID")
        candidates = []
        for item in data:
            if not isinstance(item, dict):
                continue
            url = str(item.get("detail_url") or "")
            parsed = urlparse(url)
            if (parsed.scheme != "https" or parsed.hostname != "empresa.co.computrabajo.com"
                    or parsed.path.casefold() != "/company/matchcvdetail/matchdetail"):
                continue
            if not str(item.get("external_id") or "").strip():
                continue
            candidates.append(item)
        return candidates

    def discover_visible_candidates(self) -> list[dict]:
        return self._call(self._discover_visible_candidates_async(), timeout=30.0)


    async def _discover_all_candidates_async(self, *, max_pages: int = 500,
                                             stop_requested=None,
                                             discovery_progress=None) -> dict:
        """Visit accessible offer indexes and all discoverable candidate pages.

        Offers are merely navigation: we only return unique candidate profiles.
        Dynamic next-page controls and listing tabs are clicked in the
        authenticated browser session. This does not bypass expired offers.
        """
        from collections import deque
        from urllib.parse import parse_qs
        from .computrabajo_directory import (
            OFFERS_START, CANDIDATES_PATH, DIRECTORY_SCAN_JS,
            pagination_next_js, directory_url, candidate_detail_url, tab_click_js,
        )

        if not 1 <= max_pages <= 1000:
            raise ValueError("COMPUTRABAJO_INVALID_PAGE_LIMIT")
        pending = deque([(OFFERS_START, None)])
        scheduled = {(OFFERS_START, None)}
        visited_tasks = set()
        tab_scans = set()
        found = {}
        offer_urls = set()
        offer_expected_counts = {}
        offer_discovered_ids = {}
        blocked_pages = pages = candidate_pages = listing_pages = 0
        unresolved_pagination = 0
        cancelled = False

        async def scan(cdp):
            page = await self._evaluate(cdp, DIRECTORY_SCAN_JS)
            if not isinstance(page, dict):
                raise RuntimeError("COMPUTRABAJO_DISCOVERY_INVALID")
            if page.get("error"):
                raise ValueError(str(page["error"]))
            if not isinstance(page.get("candidates"), list):
                raise RuntimeError("COMPUTRABAJO_DISCOVERY_INVALID")
            return page

        def signature(page):
            # Used for in-memory loop detection; never written to disk.
            return (
                tuple(sorted(str(c.get("external_id") or "")
                    for c in page.get("candidates", []) if isinstance(c, dict))),
                tuple(sorted(page.get("offer_links", []))),
                tuple(sorted(page.get("page_links", []))),
                str(page.get("active_page") or ""),
                str(page.get("active_tab") or ""),
            )

        def enqueue(url, tab=None):
            safe = directory_url(url)
            if safe is None:
                return
            task = (safe, tab)
            if task not in scheduled:
                scheduled.add(task)
                pending.append(task)

        while pending and pages < max_pages:
            if stop_requested and stop_requested():
                cancelled = True
                break
            url, tab = pending.popleft()
            if (url, tab) in visited_tasks:
                continue
            visited_tasks.add((url, tab))
            if directory_url(url) is None:
                continue
            await self._open_portal(url)
            cdp = await self._ensure_started()
            tab_base_signature = None
            if tab is not None:
                original = await scan(cdp)
                tab_base_signature = signature(original)
                activated = await self._evaluate(
                    cdp, tab_click_js(
                        tab,
                        candidate_list=urlparse(url).path.casefold().rstrip("/") == CANDIDATES_PATH,
                    )
                )
                if not isinstance(activated, dict) or not activated.get("clicked"):
                    unresolved_pagination += 1
                    continue
                await asyncio.sleep(0.6)

            previous_signature = tab_base_signature
            last_numeric_page = 1
            while pages < max_pages:
                if stop_requested and stop_requested():
                    cancelled = True
                    break
                cdp = await self._ensure_started()
                page = None
                # After clicking a JS page control, wait for the DOM to change.
                # Fail closed rather than repeatedly ingest the same page.
                for attempt in range(14 if previous_signature else 6):
                    page = await scan(cdp)
                    if page.get("access_denied"):
                        break
                    if previous_signature is not None:
                        if signature(page) != previous_signature:
                            break
                    elif (page.get("candidates") or page.get("offer_links") or
                          page.get("page_links") or page.get("tabs_js") or
                          page.get("js_next") or attempt == 5):
                        break
                    await asyncio.sleep(0.4)
                    cdp = await self._ensure_started()
                if previous_signature is not None and not page.get("access_denied") and (
                        signature(page) == previous_signature):
                    unresolved_pagination += 1
                    break
                previous_signature = signature(page)
                pages += 1
                if discovery_progress:
                    discovery_progress({
                        "pages": pages, "offers_found": len(offer_urls),
                        "candidates_found": len(found), "blocked_pages": blocked_pages,
                    })
                if page.get("access_denied"):
                    blocked_pages += 1
                    break
                current_path = urlparse(url).path.casefold().rstrip("/")
                ids = parse_qs(urlparse(url).query).get("oi", [])
                offer_key = ids[0].casefold() if ids else None
                if current_path == CANDIDATES_PATH:
                    candidate_pages += 1
                    count = page.get("reported_received")
                    if (offer_key and type(count) is int and 0 <= count <= 1000000):
                        offer_expected_counts[offer_key] = max(
                            offer_expected_counts.get(offer_key, 0), count
                        )
                else:
                    listing_pages += 1
                for candidate in page["candidates"]:
                    if (isinstance(candidate, dict) and candidate_detail_url(
                            candidate.get("detail_url"), candidate.get("external_id"))):
                        external_id = str(candidate["external_id"]).casefold()
                        found.setdefault(external_id, candidate)
                        if offer_key and current_path == CANDIDATES_PATH:
                            offer_discovered_ids.setdefault(offer_key, set()).add(external_id)
                for candidate_listing in page.get("offer_links", []):
                    safe = directory_url(candidate_listing)
                    if safe and urlparse(safe).path.casefold().rstrip("/") == CANDIDATES_PATH:
                        offer_urls.add(safe)
                        enqueue(safe)
                for next_url in page.get("page_links", []):
                    enqueue(next_url)
                if tab is None:
                    # Scan candidate status tabs once per provider offer, not
                    # once for each page of a large paginated listing.
                    ids = parse_qs(urlparse(url).query).get("oi", [])
                    tab_group = (current_path, ids[0].casefold() if ids else url)
                    if tab_group not in tab_scans:
                        tab_scans.add(tab_group)
                        for next_tab in page.get("tabs_js", []):
                            if isinstance(next_tab, str):
                                enqueue(url, next_tab)
                # Old DOM adapters signal unsupported pagination instead of
                # js_next; treat that as partial, not as "fully synchronized".
                if page.get("unsupported_pagination"):
                    unresolved_pagination += 1
                if not page.get("js_next"):
                    break
                clicked = await self._evaluate(
                    cdp, pagination_next_js(after_page=last_numeric_page)
                )
                if not isinstance(clicked, dict) or not clicked.get("clicked"):
                    unresolved_pagination += 1
                    break
                target_page = clicked.get("target_page")
                if (type(target_page) is int and 1 <= target_page <= 10000):
                    last_numeric_page = max(last_numeric_page, target_page)
                await asyncio.sleep(0.45)
            if cancelled:
                break
            await asyncio.sleep(0.1)

        incomplete_offers = sum(
            len(offer_discovered_ids.get(key, set())) < count
            for key, count in offer_expected_counts.items()
        )
        if not found and not cancelled:
            raise ValueError(
                "COMPUTRABAJO_OFFER_EXPIRED_ACCESS_DENIED"
                if blocked_pages else "COMPUTRABAJO_NO_CANDIDATES_DISCOVERED"
            )
        return {
            "candidates": list(found.values()),
            "pages": pages,
            "candidate_pages": candidate_pages,
            "listing_pages": listing_pages,
            "offers_found": len(offer_urls),
            "blocked_pages": blocked_pages,
            "unresolved_pagination": unresolved_pagination,
            "reported_received_total": sum(offer_expected_counts.values()),
            "discovered_with_reported_total": sum(
                len(offer_discovered_ids.get(key, set()))
                for key in offer_expected_counts
            ),
            "offers_with_missing_candidates": incomplete_offers,
            "cancelled": cancelled,
            "partial": (
                bool(pending) or unresolved_pagination > 0 or
                blocked_pages > 0 or incomplete_offers > 0 or
                cancelled or pages >= max_pages
            ),
        }

    def discover_all_candidates(self, *, max_pages: int = 500,
                                stop_requested=None, discovery_progress=None) -> dict:
        return self._call(
            self._discover_all_candidates_async(
                max_pages=max_pages, stop_requested=stop_requested,
                discovery_progress=discovery_progress
            ), timeout=max(300.0, max_pages * 12.0),
        )

    async def _collect_candidate_async(self, candidate: dict) -> dict:
        """Navigate to one discovered profile and obtain CV bytes within browser session.

        Prefer the provider attachment; PDF fallback only on unsupported/missing file.
        """
        detail_url = str(candidate.get("detail_url") or "")
        parsed = urlparse(detail_url)
        if (parsed.scheme != "https" or parsed.hostname != "empresa.co.computrabajo.com"
                or parsed.path.lower() != "/company/matchcvdetail/matchdetail"):
            raise ValueError("COMPUTRABAJO_INVALID_CANDIDATE_URL")
        cdp = await self._ensure_started()
        await cdp.cdp_client.send.Page.navigate(
            params={"url": detail_url}, session_id=cdp.session_id,
        )
        await self._wait_ready(cdp)
        info = await self._evaluate(cdp, """(() => {
            if (location.hostname !== 'empresa.co.computrabajo.com' ||
                location.pathname.toLowerCase() !== '/company/matchcvdetail/matchdetail') {
                return {error: 'COMPUTRABAJO_PROFILE_REQUIRED'};
            }
            const content = (document.body?.innerText || '').toLowerCase();
            if (/su oferta de empleo ha vencido|oferta de empleo ha vencido|contratar una membresía/i.test(content))
                return {error: 'COMPUTRABAJO_OFFER_EXPIRED_ACCESS_DENIED'};
            const links = [...document.querySelectorAll('a.js_download_file[href], a[href*="CvDownloader"]')];
            const valid = links.map(a => {
                try { return new URL(a.href, location.href); }
                catch (_) { return null; }
            }).filter(u => u && u.origin === location.origin &&
                u.pathname.toLowerCase() === '/company/cvdownloader/company/cvdetail/download' &&
                u.searchParams.has('ims'));
            const name = (document.querySelector('h1.fs22, h1')?.textContent || '').trim();
            return {name: name.slice(0, 180),
                    attachment_url: valid[0]?.href || ''};
        })()""")
        if not isinstance(info, dict):
            raise RuntimeError("COMPUTRABAJO_PROFILE_INVALID")
        if info.get("error"):
            raise RuntimeError(str(info["error"]))
        name = str(candidate.get("candidate_name") or info.get("name") or "").strip()
        if not name:
            raise RuntimeError("COMPUTRABAJO_NAME_MISSING")
        if not info.get("attachment_url") and not info.get("name"):
            raise RuntimeError("COMPUTRABAJO_PROFILE_CONTENT_UNAVAILABLE")
        if info.get("attachment_url"):
            encoded = json.dumps(str(info["attachment_url"]))
            result = await self._evaluate(cdp, """(async () => {
                const url = """ + encoded + """;
                try {
                    const response = await fetch(url, {credentials: 'same-origin'});
                    const type = response.headers.get('content-type') || '';
                    if (response.status === 401 || response.status === 403)
                        return {access_denied: true};
                    if (!response.ok || /text\\/html|application\\/json/i.test(type))
                        return {unsupported: true};
                    const buffer = await response.arrayBuffer();
                    if (buffer.byteLength < 8 || buffer.byteLength > 15 * 1024 * 1024)
                        return {unsupported: true};
                    const view = new Uint8Array(buffer);
                    let raw = '';
                    for (let i=0; i<view.length; i+=8192)
                        raw += String.fromCharCode(...view.subarray(i, i+8192));
                    return {content: btoa(raw), type};
                } catch (_) { return {unsupported: true}; }
            })()""")
            if isinstance(result, dict) and result.get("access_denied"):
                raise RuntimeError("COMPUTRABAJO_CV_ACCESS_DENIED")
            if isinstance(result, dict) and result.get("content"):
                raw = base64.b64decode(result["content"], validate=True)
                if raw.lstrip().startswith(b"%PDF-"):
                    return dict(name=name, data=raw, filename="computrabajo-cv.pdf",
                                content_type="application/pdf", kind="attached")
                if raw.startswith(b"PK") and len(raw) <= 15 * 1024 * 1024:
                    return dict(name=name, data=raw, filename="computrabajo-cv.docx",
                                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                kind="attached")
        response = await cdp.cdp_client.send.Page.printToPDF(
            params={"printBackground": True, "preferCSSPageSize": True},
            session_id=cdp.session_id,
        )
        encoded = response.get("data") if isinstance(response, dict) else None
        if not encoded:
            raise RuntimeError("COMPUTRABAJO_PRINT_EMPTY")
        raw = base64.b64decode(encoded, validate=True)
        if not raw.startswith(b"%PDF-") or len(raw) > 15 * 1024 * 1024:
            raise RuntimeError("COMPUTRABAJO_PRINT_INVALID")
        return dict(name=name, data=raw, filename="computrabajo-profile.pdf",
                    content_type="application/pdf", kind="profile")

    def collect_candidate(self, candidate: dict) -> dict:
        return self._call(self._collect_candidate_async(candidate), timeout=90.0)

    async def _save_visible_profile_pdf_async(self) -> str:
        """Export a user-opened Computrabajo profile, without bulk collection."""
        cdp = await self._ensure_started()
        page = await self._page_metadata(cdp)
        url = str(page.get("url") or "")
        parsed = urlparse(url)
        if (
            parsed.hostname != "empresa.co.computrabajo.com"
            or parsed.path.casefold() not in (
                "/company/matchcvdetail/matchdetail",
                "/company/matchcvdetail/matchprint",
            )
        ):
            raise ValueError("COMPUTRABAJO_PROFILE_REQUIRED")
        response = await cdp.cdp_client.send.Page.printToPDF(
            params={"printBackground": True, "preferCSSPageSize": True},
            session_id=cdp.session_id,
        )
        encoded = response.get("data") if isinstance(response, dict) else None
        if not encoded:
            raise RuntimeError("COMPUTRABAJO_PDF_EMPTY")
        data = base64.b64decode(encoded, validate=True)
        if not data.startswith(b"%PDF-") or len(data) > 20 * 1024 * 1024:
            raise RuntimeError("COMPUTRABAJO_PDF_INVALID")
        folder = self._profile_dir.parent / "exports" / "computrabajo"
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        destination = folder / f"profile-{stamp}.pdf"
        destination.write_bytes(data)
        return str(destination)

    def save_visible_profile_pdf(self) -> str:
        return self._call(self._save_visible_profile_pdf_async(), timeout=60.0)

    async def _page_metadata(self, cdp) -> dict:
        value = await self._evaluate(
            cdp,
            "(() => ({url: location.href, title: document.title || ''}))()",
        )
        return value if isinstance(value, dict) else {}

    async def _start_diagnostic_async(self) -> None:
        self._diagnostic_events = []
        self._diagnostic_started_at = datetime.now(timezone.utc).isoformat()
        self._diagnostic_active = True
        await self._open_portal()

    def start_diagnostic(self) -> None:
        self._call(self._start_diagnostic_async())

    def poll_diagnostic(self) -> None:
        if not self._diagnostic_active:
            return
        self._call(self._ensure_started(), timeout=15.0)

    async def _stop_diagnostic_async(self) -> str | None:
        if not self._diagnostic_active:
            return self._last_diagnostic_path
        self._diagnostic_active = False
        cdp = await self._ensure_started()
        diagnostics_dir = self._profile_dir.parent / "diagnostics"
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        json_path = (
            diagnostics_dir
            / f"computrabajo-flow-diagnostic-{stamp}.json"
        )
        png_path = (
            diagnostics_dir
            / f"computrabajo-flow-diagnostic-{stamp}.png"
        )
        page = await self._page_metadata(cdp)
        screenshot_saved = False
        if self._config.diagnostic_screenshots:
            try:
                shot = await cdp.cdp_client.send.Page.captureScreenshot(
                    params={"format": "png"},
                    session_id=cdp.session_id,
                )
                encoded = shot.get("data") if isinstance(shot, dict) else None
                if encoded:
                    png_path.write_bytes(base64.b64decode(encoded))
                    screenshot_saved = True
            except Exception:
                pass

        payload = {
            "captured_at_utc": datetime.now(timezone.utc).isoformat(),
            "started_at_utc": self._diagnostic_started_at,
            "provider": "computrabajo",
            "driver": "browser-use-cdp",
            "events": list(self._diagnostic_events),
            "page": {
                "url": self._safe_diagnostic_url(page.get("url")),
                "title": str(page.get("title") or "")[:300],
            },
            "screenshot": str(png_path) if screenshot_saved else "",
            "privacy": {
                "query_strings_persisted": False,
                "cookies_persisted": False,
                "authorization_headers_persisted": False,
                "response_bodies_persisted": False,
            },
        }
        try:
            json_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self._last_diagnostic_path = str(json_path)
            return self._last_diagnostic_path
        except Exception:
            return None

    def stop_diagnostic(self) -> str | None:
        return self._call(
            self._stop_diagnostic_async(),
            timeout=30.0,
        )

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
