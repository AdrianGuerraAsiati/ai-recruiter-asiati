from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

from tools.indeed_resume_agent.browser import _resolve_browser_executable
from tools.indeed_resume_agent.browser_use_driver import _load_browser_session_class


_SELF_TEST_SERVICE = "ASIATI Resume Agent Self Test"
_SELF_TEST_USERNAME = "qa-preflight"



async def _browser_use_check_with_retry(
    chrome: Path,
    profile_root: Path,
    *,
    attempts: int = 2,
) -> bool:
    """Retry only the isolated packaged preflight browser cold start.

    GitHub-hosted Windows runners can occasionally take more than Browser Use's
    internal 30 second launch budget on the first cold Chrome start. Each retry
    gets a fresh profile. Production browser behavior is unchanged.
    """
    last_error: Exception | None = None
    for attempt in range(max(1, int(attempts))):
        try:
            ok = await _browser_use_check(
                chrome,
                profile_root / f"attempt-{attempt + 1}",
            )
            if ok:
                return True
        except Exception as exc:
            last_error = exc

        if attempt + 1 < max(1, int(attempts)):
            await asyncio.sleep(1.0)

    if last_error is not None:
        raise last_error
    return False


async def _browser_use_check(chrome: Path, profile_dir: Path) -> bool:
    session_class = _load_browser_session_class()
    browser = session_class(
        executable_path=str(chrome),
        user_data_dir=str(profile_dir),
        headless=True,
        accept_downloads=True,
        auto_download_pdfs=False,
        enable_default_extensions=False,
        captcha_solver=False,
        chromium_sandbox=True,
        highlight_elements=False,
        dom_highlight_elements=False,
    )
    try:
        await browser.start()
        cdp = await browser.get_or_create_cdp_session(
            browser.agent_focus_target_id,
            focus=True,
        )
        await cdp.cdp_client.send.Runtime.enable(session_id=cdp.session_id)
        result = await cdp.cdp_client.send.Runtime.evaluate(
            params={
                "expression": (
                    "document.title='ASIATI packaged preflight';"
                    "document.body.innerHTML='<div id=qa>resume-agent-ok</div>';"
                    "({title: document.title, text: document.body.innerText})"
                ),
                "returnByValue": True,
                "awaitPromise": True,
            },
            session_id=cdp.session_id,
        )
        payload = result.get("result", {}) if isinstance(result, dict) else {}
        value = payload.get("value", {}) if isinstance(payload, dict) else {}
        return (
            isinstance(value, dict)
            and value.get("title") == "ASIATI packaged preflight"
            and value.get("text") == "resume-agent-ok"
        )
    finally:
        try:
            await browser.stop()
        except Exception:
            pass


def run_self_test() -> int:
    """Validate packaged Windows integrations without contacting production."""
    token = f"self-test-{os.getpid()}-" + ("x" * 40)
    keyring = None

    try:
        import keyring as loaded_keyring

        keyring = loaded_keyring
        keyring.set_password(_SELF_TEST_SERVICE, _SELF_TEST_USERNAME, token)
        if keyring.get_password(_SELF_TEST_SERVICE, _SELF_TEST_USERNAME) != token:
            return 21

        chrome = Path(_resolve_browser_executable("chrome"))
        if not chrome.is_file():
            return 31

        with tempfile.TemporaryDirectory(
            prefix="asiati-resume-agent-self-test-"
        ) as temp:
            ok = asyncio.run(
                _browser_use_check_with_retry(
                    chrome,
                    Path(temp) / "browser-use-profile",
                )
            )
            if not ok:
                return 41
        return 0
    except Exception:
        return 1
    finally:
        if keyring is not None:
            try:
                keyring.delete_password(_SELF_TEST_SERVICE, _SELF_TEST_USERNAME)
            except Exception:
                pass
