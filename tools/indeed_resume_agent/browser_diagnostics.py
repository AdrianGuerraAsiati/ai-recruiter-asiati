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


def diagnostic_request_event(request) -> dict:
    return {
        "kind": "request",
        "method": str(getattr(request, "method", "") or "")[:16],
        "resource_type": str(getattr(request, "resource_type", "") or "")[:40],
        "url": safe_diagnostic_url(getattr(request, "url", "")),
    }


def diagnostic_response_event(response) -> dict:
    request = getattr(response, "request", None)
    headers = getattr(response, "headers", {}) or {}
    content_type = str(
        headers.get("content-type") or headers.get("Content-Type") or ""
    )[:200]
    content_disposition = safe_diagnostic_text(
        headers.get("content-disposition")
        or headers.get("Content-Disposition")
        or "",
        limit=300,
    )
    safe_url = safe_diagnostic_url(getattr(response, "url", ""))
    event = {
        "kind": "response",
        "status": int(getattr(response, "status", 0) or 0),
        "resource_type": str(
            getattr(request, "resource_type", "") or ""
        )[:40],
        "url": safe_url,
        "content_type": content_type,
        "content_disposition": content_disposition,
        "content_length": str(
            headers.get("content-length")
            or headers.get("Content-Length")
            or ""
        )[:40],
    }

    relevant = any(
        marker in safe_url.casefold()
        for marker in ("resume", "candidate", "download", ".pdf")
    ) or any(
        marker in content_type.casefold()
        for marker in ("pdf", "octet-stream")
    )
    if relevant and event["status"] < 400:
        try:
            body = bytes(response.body() or b"")
            event["body_size"] = len(body)
            event["starts_with_pdf"] = body.startswith(b"%PDF-")
            event["first_bytes_hex"] = body[:24].hex()
        except Exception as exc:
            event["body_probe_error"] = safe_diagnostic_text(exc, limit=160)
    return event


def diagnostic_controls(page) -> list[dict[str, str]]:
    controls: list[dict[str, str]] = []
    try:
        items = page.locator('button, a, [role="button"], iframe, embed, object')
        count = min(int(items.count()), 120)
    except Exception:
        return controls

    for index in range(count):
        try:
            node = items.nth(index)
            tag = str(node.evaluate("el => el.tagName.toLowerCase()") or "")[:30]
            if tag not in {"iframe", "embed", "object"} and not node.is_visible():
                continue
            href = (
                node.get_attribute("href")
                or node.get_attribute("src")
                or node.get_attribute("data")
                or ""
            )
            text = ""
            if tag not in {"iframe", "embed", "object"}:
                text = node.inner_text(timeout=500)
            controls.append(
                {
                    "tag": tag,
                    "role": str(node.get_attribute("role") or "")[:80],
                    "text": safe_diagnostic_text(text, limit=220),
                    "aria_label": safe_diagnostic_text(
                        node.get_attribute("aria-label") or "",
                        limit=220,
                    ),
                    "data_testid": safe_diagnostic_text(
                        node.get_attribute("data-testid") or "",
                        limit=160,
                    ),
                    "target": safe_diagnostic_url(href),
                }
            )
        except Exception:
            continue
    return controls
