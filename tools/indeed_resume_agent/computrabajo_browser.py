from __future__ import annotations

import asyncio
import base64
import concurrent.futures
import hashlib
import json
import re
import threading
import time
from dataclasses import dataclass
from urllib.parse import parse_qs, urljoin, urlsplit

from .browser_runtime import resolve_browser_executable
from .config import AgentConfig
from .credential_store import (
    ProviderCredentialMissing,
    read_computrabajo_credentials,
)

_CHALLENGE_MARKERS = (
    "captcha",
    "verify you are human",
    "verifica que eres humano",
    "verificación de seguridad",
    "verificacion de seguridad",
)
_DETAIL_PATH_MARKERS = ("/company/cvdetail/detail", "/company/cvdetail/print")


@dataclass(frozen=True)
class ComputrabajoSyncResult:
    discovered: int
    imported: int
    existing: int
    skipped: int
    failed: int


def _runtime_value(result):
    if isinstance(result, dict):
        payload = result.get("result")
        if isinstance(payload, dict):
            return payload.get("value")
    return None


def _configure_browser_environment() -> None:
    import os

    os.environ["BROWSER_USE_SETUP_LOGGING"] = "false"
    os.environ["ANONYMIZED_TELEMETRY"] = "false"
    os.environ["BROWSER_USE_CLOUD_SYNC"] = "false"


def _load_browser_session_class():
    _configure_browser_environment()
    try:
        import browser_use.browser.profile as browser_use_profile

        args = getattr(browser_use_profile, "CHROME_DEFAULT_ARGS", None)
        if isinstance(args, list):
            while "--extensions-on-chrome-urls" in args:
                args.remove("--extensions-on-chrome-urls")
    except Exception:
        pass

    from browser_use.browser.session import BrowserSession

    return BrowserSession


def _official_url(raw: str, *, fallback: str) -> str:
    value = str(raw or "").strip()
    if not value:
        return fallback
    try:
        parsed = urlsplit(value)
    except Exception:
        return fallback
    host = str(parsed.hostname or "").casefold()
    allowed = (
        host == "computrabajo.com.co"
        or host.endswith(".computrabajo.com.co")
        or host == "computrabajo.com"
        or host.endswith(".computrabajo.com")
    )
    if parsed.scheme.casefold() != "https" or not allowed:
        return fallback
    return value


def _external_candidate_id(url: str) -> str:
    """Build an application identity so one person may belong to multiple jobs."""
    parsed = urlsplit(str(url or ""))
    query = {str(key).casefold(): values for key, values in parse_qs(parsed.query).items()}

    candidate_key = None
    candidate_value = None
    for key in ("ids", "ims", "id", "cv", "candidateid"):
        values = query.get(key)
        if values and str(values[0]).strip():
            candidate_key = key
            candidate_value = str(values[0]).strip()
            break

    offer_values = query.get("oi") or query.get("offerid") or query.get("jobid")
    offer_value = (
        str(offer_values[0]).strip()
        if offer_values and str(offer_values[0]).strip()
        else None
    )

    if candidate_value and offer_value:
        return f"application:{offer_value}:{candidate_key}:{candidate_value}"
    if candidate_value:
        return f"{candidate_key}:{candidate_value}"

    digest = hashlib.sha256(str(url).encode("utf-8")).hexdigest()
    return f"url:{digest[:40]}"


def _clean_name(value: str | None) -> str:
    text = " ".join(str(value or "").split()).strip()
    text = re.sub(r"^(?:curr[ií]culum|hoja de vida)\s+de\s+", "", text, flags=re.I)
    return text[:1000]


def _guess_job_title(detail: dict, row_text: str) -> str:
    direct = " ".join(str(detail.get("jobTitle") or "").split()).strip()
    if direct:
        return direct[:1000]

    for raw in (str(detail.get("body") or ""), str(row_text or "")):
        match = re.search(r"(?:^|\n)\s*Aviso\s+([^\n]{2,250})", raw, flags=re.I)
        if match:
            return " ".join(match.group(1).split())[:1000]
        match = re.search(
            r"(?:vacante|oferta|cargo)\s*[:\-]\s*([^\n|]{2,250})",
            raw,
            flags=re.I,
        )
        if match:
            return " ".join(match.group(1).split())[:1000]
    return ""


def _guess_location(detail: dict) -> str | None:
    direct = " ".join(str(detail.get("location") or "").split()).strip()
    if direct:
        return direct[:1000]
    body = str(detail.get("body") or "")
    match = re.search(r"Localizaci[oó]n\s*[:\-]?\s*([^\n]{2,160})", body, flags=re.I)
    if match:
        return " ".join(match.group(1).split())[:1000]
    return None


class ComputrabajoBrowserUse:
    """Visible Chrome adapter for recruiter-owned Computrabajo candidate pages.

    Navigation and extraction are deterministic. Authentication credentials stay
    in Windows Credential Manager and are only injected into the visible login
    form. CAPTCHA/security challenges are never bypassed.
    """

    def __init__(self, config: AgentConfig, *, browser_session_class=None) -> None:
        self._config = config
        self._browser_session_class = browser_session_class
        self._browser = None
        self._closed = False
        self._loop = asyncio.new_event_loop()
        self._loop_ready = threading.Event()
        self._loop_thread = threading.Thread(
            target=self._run_loop,
            name="asiati-computrabajo-browser",
            daemon=True,
        )
        self._loop_thread.start()
        self._loop_ready.wait(timeout=5.0)

    @property
    def browser_label(self) -> str:
        return "Google Chrome" if self._config.browser_name == "chrome" else "Microsoft Edge"

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop_ready.set()
        self._loop.run_forever()
        pending = asyncio.all_tasks(self._loop)
        for task in pending:
            task.cancel()
        if pending:
            self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        self._loop.close()

    def _call(self, coro, *, timeout: float | None = None):
        if self._closed:
            raise RuntimeError("COMPUTRABAJO_BROWSER_CLOSED")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(
                timeout=timeout
                or max(90.0, float(self._config.sync_request_timeout_seconds))
            )
        except concurrent.futures.TimeoutError as exc:
            future.cancel()
            raise RuntimeError("COMPUTRABAJO_BROWSER_TIMEOUT") from exc

    async def _ensure_started(self):
        if self._browser is None:
            session_class = self._browser_session_class or _load_browser_session_class()
            profile_dir = self._config.computrabajo_profile_dir
            if profile_dir is None:
                profile_dir = self._config.browser_profile_dir.parent / (
                    f"computrabajo-profile-{self._config.browser_name}"
                )
            profile_dir.mkdir(parents=True, exist_ok=True)
            self._browser = session_class(
                executable_path=resolve_browser_executable(self._config.browser_name),
                user_data_dir=str(profile_dir.resolve()),
                headless=False,
                allowed_domains=[
                    "computrabajo.com",
                    "*.computrabajo.com",
                    "computrabajo.com.co",
                    "*.computrabajo.com.co",
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
            10.0,
            float(self._config.request_timeout_seconds),
        )
        while time.monotonic() < deadline:
            ready = await self._evaluate(cdp, "document.readyState")
            if ready in {"interactive", "complete"}:
                await asyncio.sleep(0.5)
                return
            await asyncio.sleep(0.25)
        raise RuntimeError("COMPUTRABAJO_NAVIGATION_TIMEOUT")

    async def _navigate(self, cdp, url: str) -> None:
        target = _official_url(url, fallback=self._config.computrabajo_base_url)
        await cdp.cdp_client.send.Page.navigate(
            params={"url": target},
            session_id=cdp.session_id,
        )
        await self._wait_ready(cdp)

    async def _page_state(self, cdp) -> dict:
        value = await self._evaluate(
            cdp,
            r"""(() => ({
  url: location.href,
  title: document.title || '',
  body: String(document.body?.innerText || '').slice(0, 20000),
  hasPassword: !!Array.from(document.querySelectorAll('input[type="password"]'))
    .find((el) => el.offsetParent !== null),
}))()""",
        )
        return value if isinstance(value, dict) else {}

    async def _requires_human(self, cdp) -> bool:
        state = await self._page_state(cdp)
        body = str(state.get("body") or "").casefold()
        return any(marker in body for marker in _CHALLENGE_MARKERS)

    async def _login(self) -> str:
        cdp = await self._ensure_started()
        state = await self._page_state(cdp)
        if not state.get("hasPassword"):
            await self._navigate(cdp, self._config.computrabajo_base_url)
            state = await self._page_state(cdp)
        if await self._requires_human(cdp):
            raise RuntimeError("COMPUTRABAJO_HUMAN_REQUIRED")

        if not state.get("hasPassword"):
            body = str(state.get("body") or "").casefold()
            dashboard_markers = (
                "mis ofertas",
                "buscar candidatos",
                "reclutamiento",
                "publicar una oferta",
            )
            if sum(marker in body for marker in dashboard_markers) >= 2:
                return "ALREADY_AUTHENTICATED"

            login_url = await self._evaluate(
                cdp,
                r"""(() => {
  const visible = (el) => !!el && el.offsetParent !== null;
  const anchors = Array.from(document.querySelectorAll('a[href]')).filter(visible);
  const candidate = anchors.find((a) =>
    /reclutadores|empresas|ingresar|iniciar sesi[oó]n|login/i.test(
      String(a.innerText || a.textContent || '')
    )
  );
  return candidate?.href || '';
})()""",
            )
            if login_url:
                await self._navigate(cdp, str(login_url))
                state = await self._page_state(cdp)

        if await self._requires_human(cdp):
            raise RuntimeError("COMPUTRABAJO_HUMAN_REQUIRED")
        if not state.get("hasPassword"):
            body = str(state.get("body") or "").casefold()
            dashboard_markers = (
                "mis ofertas",
                "buscar candidatos",
                "reclutamiento",
                "publicar una oferta",
            )
            if sum(marker in body for marker in dashboard_markers) >= 2:
                return "ALREADY_AUTHENTICATED"
            raise RuntimeError("COMPUTRABAJO_LOGIN_FORM_CHANGED")

        username, password = read_computrabajo_credentials()
        username_json = json.dumps(username)
        password_json = json.dumps(password)
        result = await self._evaluate(
            cdp,
            f"""(() => {{
  const visible = (el) => !!el && el.offsetParent !== null && !el.disabled;
  const email = Array.from(document.querySelectorAll(
    'input[type="email"],input[name*="mail" i],input[name*="user" i],input[autocomplete="username"]'
  )).find(visible);
  const password = Array.from(document.querySelectorAll(
    'input[type="password"],input[autocomplete="current-password"]'
  )).find(visible);
  if (!email || !password) return {{submitted:false, reason:'FORM_NOT_FOUND'}};
  const setValue = (el, value) => {{
    const setter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype, 'value'
    )?.set;
    if (setter) setter.call(el, value); else el.value = value;
    el.dispatchEvent(new Event('input', {{bubbles:true}}));
    el.dispatchEvent(new Event('change', {{bubbles:true}}));
  }};
  setValue(email, {username_json});
  setValue(password, {password_json});
  const form = password.closest('form') || email.closest('form');
  const button = form
    ? Array.from(form.querySelectorAll('button,input[type="submit"]')).find(visible)
    : Array.from(document.querySelectorAll('button,input[type="submit"]')).find(
        (el) => visible(el) && /ingresar|iniciar|entrar|login/i.test(el.innerText || el.value || '')
      );
  if (button) button.click();
  else if (form?.requestSubmit) form.requestSubmit();
  else return {{submitted:false, reason:'SUBMIT_NOT_FOUND'}};
  return {{submitted:true}};
}})()""",
        )
        if not isinstance(result, dict) or not result.get("submitted"):
            raise RuntimeError("COMPUTRABAJO_LOGIN_FORM_CHANGED")
        await asyncio.sleep(2.0)
        await self._wait_ready(cdp)
        if await self._requires_human(cdp):
            raise RuntimeError("COMPUTRABAJO_HUMAN_REQUIRED")
        state = await self._page_state(cdp)
        if state.get("hasPassword"):
            raise RuntimeError("COMPUTRABAJO_LOGIN_REJECTED")
        return "AUTHENTICATED"

    async def _open(self) -> str:
        cdp = await self._ensure_started()
        await self._navigate(cdp, self._config.computrabajo_base_url)
        try:
            return await self._login()
        except ProviderCredentialMissing:
            return "CREDENTIALS_REQUIRED"

    def open(self) -> str:
        return str(self._call(self._open()))

    async def _candidate_links(self, cdp) -> list[dict]:
        value = await self._evaluate(
            cdp,
            r"""(() => {
  const absolute = (href) => {
    try { return new URL(href, location.href).href; } catch { return ''; }
  };
  const candidates = [];
  const seen = new Set();
  const current = String(location.href || '');
  if (//Company/CvDetail/(?:Detail|Print)/i.test(current)) {
    seen.add(current);
    candidates.push({url: current, rowText: String(document.body?.innerText || '').slice(0, 1200)});
  }
  for (const anchor of Array.from(document.querySelectorAll('a[href]'))) {
    const url = absolute(anchor.getAttribute('href'));
    if (!//Company/CvDetail/(?:Detail|Print)/i.test(url) || seen.has(url)) continue;
    seen.add(url);
    const container = anchor.closest('tr,[role="row"],article,li,[class*="candidate" i],[class*="applicant" i]') || anchor.parentElement;
    candidates.push({
      url,
      rowText: String(container?.innerText || anchor.innerText || '').slice(0, 1200),
    });
    if (candidates.length >= 250) break;
  }
  return candidates;
})()""",
        )
        return list(value) if isinstance(value, list) else []

    async def _detail(self, cdp) -> dict:
        value = await self._evaluate(
            cdp,
            r"""(() => {
  const text = (el) => String(el?.innerText || el?.textContent || '').trim();
  const anchors = Array.from(document.querySelectorAll('a[href]'));
  const print = anchors.find((a) => //Company/CvDetail/Print/i.test(a.href));
  const offer = anchors.find((a) =>
    /offer|oferta|aviso|job/i.test(a.href) &&
    text(a).length > 1 &&
    text(a).length < 250
  );
  const heading = Array.from(document.querySelectorAll('h1,h2'))
    .map(text)
    .find((value) => /curr[ií]culum|hoja de vida/i.test(value))
    || text(document.querySelector('h1'))
    || '';
  const body = String(document.body?.innerText || '');
  const locationNode = Array.from(document.querySelectorAll('body *')).find((el) =>
    /^localizaci[oó]n\s*[:\-]?/i.test(text(el)) && text(el).length < 300
  );
  return {
    url: location.href,
    heading,
    jobTitle: text(offer),
    location: text(locationNode),
    printUrl: print?.href || '',
    body: body.slice(0, 30000),
  };
})()""",
        )
        return value if isinstance(value, dict) else {}

    async def _print_pdf(self, cdp) -> bytes:
        result = await cdp.cdp_client.send.Page.printToPDF(
            params={
                "printBackground": True,
                "preferCSSPageSize": True,
            },
            session_id=cdp.session_id,
        )
        encoded = result.get("data") if isinstance(result, dict) else None
        if not encoded:
            raise RuntimeError("COMPUTRABAJO_PRINT_FAILED")
        return base64.b64decode(encoded)

    async def _sync_current_page(self, api, *, max_candidates: int = 100) -> ComputrabajoSyncResult:
        cdp = await self._ensure_started()
        if await self._requires_human(cdp):
            raise RuntimeError("COMPUTRABAJO_HUMAN_REQUIRED")

        state = await self._page_state(cdp)
        original_url = str(state.get("url") or self._config.computrabajo_base_url)
        if state.get("hasPassword"):
            await self._login()
            state = await self._page_state(cdp)
            original_url = str(state.get("url") or original_url)

        links = await self._candidate_links(cdp)
        discovered = len(links)
        imported = existing = skipped = failed = 0

        for item in links[: max(1, min(int(max_candidates), 250))]:
            detail_url = _official_url(
                str(item.get("url") or ""),
                fallback=self._config.computrabajo_base_url,
            )
            row_text = str(item.get("rowText") or "")
            try:
                await self._navigate(cdp, detail_url)
                if await self._requires_human(cdp):
                    raise RuntimeError("COMPUTRABAJO_HUMAN_REQUIRED")
                detail = await self._detail(cdp)
                candidate_name = _clean_name(detail.get("heading"))
                job_title = _guess_job_title(detail, row_text)
                if not candidate_name or not job_title:
                    skipped += 1
                    continue

                print_url = str(detail.get("printUrl") or "").strip()
                if print_url:
                    await self._navigate(cdp, print_url)
                pdf = await self._print_pdf(cdp)
                response = api.ingest_source_candidate(
                    provider="COMPUTRABAJO",
                    source_account="corporate-recruiting",
                    external_id=_external_candidate_id(detail_url),
                    candidate_name=candidate_name,
                    job_title=job_title,
                    filename=f"{candidate_name}.pdf",
                    data=pdf,
                    content_type="application/pdf",
                    location=_guess_location(detail),
                )
                if response.get("existing"):
                    existing += 1
                else:
                    imported += 1
            except RuntimeError as exc:
                if str(exc) == "COMPUTRABAJO_HUMAN_REQUIRED":
                    raise
                failed += 1
            except Exception:
                failed += 1

        if original_url:
            try:
                await self._navigate(cdp, original_url)
            except Exception:
                pass

        return ComputrabajoSyncResult(
            discovered=discovered,
            imported=imported,
            existing=existing,
            skipped=skipped,
            failed=failed,
        )

    def sync_current_page(self, api, *, max_candidates: int = 100) -> ComputrabajoSyncResult:
        return self._call(
            self._sync_current_page(api, max_candidates=max_candidates),
            timeout=max(120.0, float(self._config.sync_request_timeout_seconds) * 4.0),
        )

    async def _async_close(self) -> None:
        browser = self._browser
        self._browser = None
        if browser is not None:
            try:
                await browser.stop()
            except Exception:
                pass

    def close(self) -> None:
        if self._closed:
            return
        try:
            self._call(self._async_close(), timeout=30.0)
        except Exception:
            pass
        self._closed = True
        try:
            self._loop.call_soon_threadsafe(self._loop.stop)
        except Exception:
            return
        self._loop_thread.join(timeout=5.0)
