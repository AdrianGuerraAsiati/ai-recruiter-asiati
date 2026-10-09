"""Authenticated Computrabajo candidate discovery contracts (no live PII)."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tools.indeed_resume_agent.computrabajo_browser import ComputrabajoBrowserUse
from tools.indeed_resume_agent import computrabajo_pagination as pagination


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


def test_full_directory_scans_links_and_skips_foreign_pages(monkeypatch):
    from unittest.mock import Mock
    b = make_browser(None)
    b._open_portal = AsyncMock()
    b._evaluate = AsyncMock(return_value={
        "candidates": [], "offer_links": [
            "https://empresa.co.computrabajo.com/Company/Offers/Match?oi=1234",
            "https://evil.example/Company/Offers/Match?oi=8888",
        ], "page_links": [], "unsupported_pagination": False})
    b._walk_offer_candidates_async = AsyncMock(return_value={
        "candidates": [{"external_id": "A" * 32, "candidate_name": "Example",
            "detail_url": "https://empresa.co.computrabajo.com/Company/MatchCvDetail/MatchDetail?ims=aaa"}],
        "pages": 1, "partial": False, "blocked": False, "expected": 1,
    })
    monkeypatch.setattr(pagination, "collect_offer_applicants", b._walk_offer_candidates_async)
    directory = asyncio.run(b._discover_all_candidates_async(max_pages=5))
    assert directory["pages"] == 2
    assert len(directory["candidates"]) == 1
    assert directory["partial"] is False
    assert b._open_portal.await_count == 1


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


def test_expired_offer_is_skipped_and_marked_partial(monkeypatch):
    b = make_browser(None)
    b._open_portal = AsyncMock()
    b._evaluate = AsyncMock(return_value={
        "candidates": [], "offer_links": [
            "https://empresa.co.computrabajo.com/Company/Offers/Match?oi=1234",
            "https://empresa.co.computrabajo.com/Company/Offers/Match?oi=5678",
        ], "page_links": [], "unsupported_pagination": False})
    b._walk_offer_candidates_async = AsyncMock(side_effect=[
        {"candidates": [], "pages": 1, "partial": True,
         "blocked": True, "expected": 0},
        {"candidates": [{
            "external_id": "A" * 32, "candidate_name": "Example",
            "detail_url": "https://empresa.co.computrabajo.com/Company/MatchCvDetail/MatchDetail?ims=abc",
        }], "pages": 1, "partial": False, "blocked": False, "expected": 1},
    ])
    monkeypatch.setattr(pagination, "collect_offer_applicants", b._walk_offer_candidates_async)
    result = asyncio.run(b._discover_all_candidates_async(max_pages=5))
    assert result["pages"] == 3
    assert result["blocked_pages"] == 1
    assert result["partial"] is True
    assert len(result["candidates"]) == 1


def test_offer_collector_covers_618_candidates_across_statuses_and_pages(monkeypatch):
    b = make_browser(None)
    b._open_portal = AsyncMock()
    b._click_candidate_listing_control = AsyncMock(return_value=True)
    original = {
        "statuses": ["recibidos", "seleccionados", "finalistas", "descartados"],
        "counts": {"recibidos": 547, "seleccionados": 6,
                   "finalistas": 0, "descartados": 65},
        "active_status": "recibidos", "reported_total": 618,
    }

    def page(state, offset, count, next_page):
        return dict(original, active_status=state, next=next_page,
            candidates=[{"external_id": f"{i:032x}",
                "candidate_name": "Test",
                "detail_url": ("https://empresa.co.computrabajo.com/"
                    f"Company/MatchCvDetail/MatchDetail?ims={i:032x}")}
                for i in range(offset, offset+count)],
            signature=f"{state}:{offset}")

    # Every status begins with a fresh first-page navigation; only an actual
    # next-page click advances the candidate view.
    received = [page("recibidos", 1, 100, True),
                page("recibidos", 101, 100, True),
                page("recibidos", 201, 100, True),
                page("recibidos", 301, 100, True),
                page("recibidos", 401, 100, True),
                page("recibidos", 501, 47, False)]
    selected = page("seleccionados", 548, 6, False)
    finalistas = page("finalistas", 554, 0, False)
    discarded = page("descartados", 554, 65, False)
    state = {"status": "recibidos", "page": 0}
    async def read(_, __):
        return (received[state["page"]] if state["status"] == "recibidos"
                else {"seleccionados": selected, "finalistas": finalistas,
                      "descartados": discarded}[state["status"]])
    async def click(_, __, kind, status=""):
        if kind == "status":
            state["status"] = status
            state["page"] = 0
        elif kind == "next":
            state["page"] += 1
        return True
    async def open_portal(url):
        state["status"] = "recibidos"
        state["page"] = 0
    async def wait(_, __, previous):
        return await read(None, None)
    b._candidate_listing_snapshot = read
    b._click_candidate_listing_control = click
    b._open_portal = open_portal
    b._wait_candidate_listing_change = wait
    monkeypatch.setattr(pagination, "_snapshot", read)
    monkeypatch.setattr(pagination, "_click", click)
    monkeypatch.setattr(pagination, "_changed", wait)
    result = asyncio.run(pagination.collect_offer_applicants(b,
        "https://empresa.co.computrabajo.com/Company/Offers/Match?oi=abc",
        max_pages=30))
    assert result["pages"] == 8
    assert result["expected"] == 618
    assert len(result["candidates"]) == 618
    assert result["partial"] is False


def test_offer_collector_reports_partial_if_next_page_missing(monkeypatch):
    b = make_browser(None)
    b._open_portal = AsyncMock()
    b._candidate_listing_snapshot = AsyncMock(return_value={
        "statuses": ["recibidos", "seleccionados", "finalistas", "descartados"],
        "counts": {"recibidos": 547, "seleccionados": 6,
                   "finalistas": 0, "descartados": 65},
        "active_status": "recibidos", "reported_total": 618,
        "signature": "page-1", "candidates": [], "next": False,
    })
    b._click_candidate_listing_control = AsyncMock(return_value=False)
    monkeypatch.setattr(pagination, "_snapshot", b._candidate_listing_snapshot)
    monkeypatch.setattr(pagination, "_click", b._click_candidate_listing_control)
    result = asyncio.run(pagination.collect_offer_applicants(b,
        "https://empresa.co.computrabajo.com/Company/Offers/Match?oi=abc",
        max_pages=30))
    assert result["expected"] == 618
    assert result["partial"] is True
