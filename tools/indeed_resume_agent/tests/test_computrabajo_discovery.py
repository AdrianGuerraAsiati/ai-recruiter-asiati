"""Authenticated Computrabajo candidate discovery contracts (no live PII)."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tools.indeed_resume_agent.computrabajo_browser import ComputrabajoBrowserUse


def make_browser(reply):
    instance = object.__new__(ComputrabajoBrowserUse)
    instance._ensure_started = AsyncMock(return_value=SimpleNamespace())
    instance._evaluate = AsyncMock(return_value=reply)
    return instance


def test_list_accepts_only_employer_candidate_links():
    browser = make_browser([
        dict(external_id="A" * 32, external_job_id="B" * 32,
             candidate_name="Example Candidate",
             detail_url="https://empresa.co.computrabajo.com/Company/MatchCvDetail/MatchDetail?ims=abc"),
        dict(external_id="C" * 32, external_job_id="B" * 32,
             candidate_name="Ignored",
             detail_url="https://evil.example/Company/MatchCvDetail/MatchDetail"),
    ])
    items = asyncio.run(browser._discover_visible_candidates_async())
    assert len(items) == 1
    assert items[0]["external_id"] == "A" * 32
    expression = browser._evaluate.call_args.args[1]
    assert "a.js-o-link.nom" in expression
    assert "/company/offers/match" in expression


def test_requires_candidate_list_page():
    browser = make_browser({"error": "COMPUTRABAJO_LIST_REQUIRED"})
    with pytest.raises(ValueError, match="COMPUTRABAJO_LIST_REQUIRED"):
        asyncio.run(browser._discover_visible_candidates_async())


def test_invalid_dom_payload_fails_closed():
    browser = make_browser(None)
    with pytest.raises(RuntimeError, match="COMPUTRABAJO_CANDIDATES_INVALID"):
        asyncio.run(browser._discover_visible_candidates_async())


def test_full_directory_scans_links_and_skips_foreign_pages():
    from unittest.mock import Mock
    b = make_browser(None)
    b._open_portal = AsyncMock()
    b._evaluate = AsyncMock(side_effect=[
        {"candidates": [], "offer_links": [
            "https://empresa.co.computrabajo.com/Company/Offers/Match?oi=1234",
            "https://evil.example/Company/Offers/Match?oi=8888",
        ], "page_links": [], "unsupported_pagination": False},
        {"candidates": [{
            "external_id": "A" * 32,
            "candidate_name": "Example",
            "detail_url": "https://empresa.co.computrabajo.com/Company/MatchCvDetail/MatchDetail?ims=aaa",
        }], "offer_links": [], "page_links": [], "unsupported_pagination": False},
    ])
    directory = asyncio.run(b._discover_all_candidates_async(max_pages=5))
    assert directory["pages"] == 2
    assert len(directory["candidates"]) == 1
    assert directory["partial"] is False
    assert b._open_portal.await_count == 2


def test_directory_reports_partial_when_pagination_cannot_be_followed():
    b = make_browser(None)
    b._open_portal = AsyncMock()
    b._evaluate = AsyncMock(return_value={
        "candidates": [{"external_id": "A" * 32, "candidate_name": "Example",
            "detail_url": "https://empresa.co.computrabajo.com/Company/MatchCvDetail/MatchDetail?ims=abc"}],
        "offer_links": [], "page_links": [], "unsupported_pagination": True,
    })
    directory = asyncio.run(b._discover_all_candidates_async(max_pages=1))
    assert directory["partial"] is True


def test_directory_requires_authenticated_employer_page():
    b = make_browser({"error": "COMPUTRABAJO_LOGIN_OR_LIST_REQUIRED"})
    b._open_portal = AsyncMock()
    with pytest.raises(ValueError, match="COMPUTRABAJO_LOGIN_OR_LIST_REQUIRED"):
        asyncio.run(b._discover_all_candidates_async(max_pages=1))


def test_expired_offer_is_skipped_and_marked_partial():
    b = make_browser(None)
    b._open_portal = AsyncMock()
    b._evaluate = AsyncMock(side_effect=[
        {"candidates": [], "offer_links": [
            "https://empresa.co.computrabajo.com/Company/Offers/Match?oi=1234",
            "https://empresa.co.computrabajo.com/Company/Offers/Match?oi=5678",
        ], "page_links": [], "unsupported_pagination": False},
        {"access_denied": "OFFER_EXPIRED", "candidates": [], "offer_links": [],
         "page_links": [], "unsupported_pagination": False},
        {"candidates": [{
            "external_id": "A" * 32, "candidate_name": "Example",
            "detail_url": "https://empresa.co.computrabajo.com/Company/MatchCvDetail/MatchDetail?ims=abc",
        }], "offer_links": [], "page_links": [],
         "unsupported_pagination": False},
    ])
    result = asyncio.run(b._discover_all_candidates_async(max_pages=5))
    assert result["pages"] == 3
    assert result["blocked_pages"] == 1
    assert result["partial"] is True
    assert len(result["candidates"]) == 1
