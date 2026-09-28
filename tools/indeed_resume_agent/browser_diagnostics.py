from __future__ import annotations

import re
from urllib.parse import urlsplit


_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(token|auth|authorization|signature|sig|api[_-]?key|code|session|cookie)=([^\s&\"']+)"
)
_URL_IN_TEXT = re.compile(r"https?://[^\s\"'<>]+")


def safe_diagnostic_url(raw_url: str | None) -> str:
    """Keep only scheme/host/path so signed query parameters are never persisted."""
    value = str(raw_url or "").strip()
    if not value:
        return ""
    try:
        parsed = urlsplit(value)
    except Exception:
        return ""
    if parsed.scheme.casefold() not in {"http", "https"}:
        return ""
    return f"{parsed.scheme.lower()}://{parsed.netloc}{parsed.path}"


def safe_diagnostic_text(value: object, *, limit: int = 500) -> str:
    """Redact URL queries and common credential-like assignments from diagnostic text."""
    text = " ".join(str(value or "").split())
    text = _URL_IN_TEXT.sub(lambda match: safe_diagnostic_url(match.group(0)), text)
    text = _SECRET_ASSIGNMENT.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)
    return text[: max(0, int(limit))]
