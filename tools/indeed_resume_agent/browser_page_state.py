from __future__ import annotations

from urllib.parse import urlsplit


_CHALLENGE_MARKERS = (
    "sign in",
    "log in",
    "iniciar sesión",
    "iniciar sesion",
    "verification",
    "verificación",
    "verificacion",
    "captcha",
    "security challenge",
    "mfa",
    "two-step",
    "two factor",
)
_URL_CHALLENGE_MARKERS = ("/login", "/signin", "challenge", "captcha", "verify")


def url_requires_human(raw_url: object) -> bool:
    url = str(raw_url or "").casefold()
    return any(marker in url for marker in _URL_CHALLENGE_MARKERS)


def requires_human(page) -> bool:
    if url_requires_human(getattr(page, "url", "")):
        return True

    # CAPTCHA/security challenges are often rendered inside an iframe after
    # the top-level document has already loaded. Checking only body text can
    # therefore miss the challenge and leave Diagnostic mode pumping the
    # automated page indefinitely.
    try:
        for frame in list(getattr(page, "frames", []) or []):
            if url_requires_human(getattr(frame, "url", "")):
                return True
    except Exception:
        pass

    try:
        challenge_nodes = page.locator(
            'iframe[src*="captcha" i], iframe[src*="challenge" i], '
            'iframe[src*="recaptcha" i], iframe[src*="hcaptcha" i], '
            '[id*="captcha" i], [class*="captcha" i]'
        )
        if int(challenge_nodes.count()) > 0:
            return True
    except Exception:
        pass

    try:
        text = str(page.locator("body").inner_text(timeout=2000) or "").casefold()
    except Exception:
        text = ""
    return any(marker in text for marker in _CHALLENGE_MARKERS)


def is_generic_recruiting_landing(page) -> bool:
    try:
        parsed = urlsplit(str(getattr(page, "url", "") or ""))
    except Exception:
        return False
    host = str(parsed.hostname or "").casefold()
    path = str(parsed.path or "").rstrip("/")
    return host == "resumes.indeed.com" and path in {"", "/"}
