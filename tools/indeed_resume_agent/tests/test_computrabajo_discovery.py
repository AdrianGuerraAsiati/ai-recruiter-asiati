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
            "detail_url": "https://empresa.co.computrabajo.com/Company/MatchCvDetail/MatchDetail?ims=" + "A" * 32,
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
            "detail_url": "https://empresa.co.computrabajo.com/Company/MatchCvDetail/MatchDetail?ims=" + "A" * 32}],
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
            "detail_url": "https://empresa.co.computrabajo.com/Company/MatchCvDetail/MatchDetail?ims=" + "A" * 32,
        }], "offer_links": [], "page_links": [],
         "unsupported_pagination": False},
    ])
    result = asyncio.run(b._discover_all_candidates_async(max_pages=5))
    assert result["pages"] == 3
    assert result["blocked_pages"] == 1
    assert result["partial"] is True
    assert len(result["candidates"]) == 1



def directory_candidate(letter):
    return {
        "external_id": letter * 32,
        "candidate_name": "Anonymous applicant",
        "detail_url": "https://empresa.co.computrabajo.com/Company/MatchCvDetail/MatchDetail?ims=" + letter * 32,
    }


def directory_page(*, candidates=(), offers=(), links=(), tabs=(),
                   js_next=False, active_page="", active_tab="", reported_received=None):
    return {
        "candidates": list(candidates), "offer_links": list(offers),
        "page_links": list(links), "tabs_js": list(tabs),
        "js_next": js_next, "active_page": active_page,
        "active_tab": active_tab, "reported_received": reported_received,
    }


def test_js_next_pagination_reads_more_candidates_without_reimporting_offers():
    browser = make_browser(None)
    browser._open_portal = AsyncMock()
    browser._evaluate = AsyncMock(side_effect=[
        directory_page(candidates=[directory_candidate("A")],
                       js_next=True, active_page="1"),
        {"clicked": True},
        directory_page(candidates=[directory_candidate("B")],
                       js_next=False, active_page="2"),
    ])
    output = asyncio.run(browser._discover_all_candidates_async(max_pages=20))
    assert output["candidate_pages"] == 0  # root offers page in fixture
    assert output["pages"] == 2
    assert len(output["candidates"]) == 2
    assert output["unresolved_pagination"] == 0
    assert output["partial"] is False


def test_js_next_stuck_marks_partial_instead_of_claiming_all():
    browser = make_browser(None)
    browser._open_portal = AsyncMock()
    first = directory_page(
        candidates=[directory_candidate("A")],
        js_next=True, active_page="1",
    )
    browser._evaluate = AsyncMock(side_effect=[first, {"clicked": True}] + [first] * 14)
    output = asyncio.run(browser._discover_all_candidates_async(max_pages=20))
    assert output["pages"] == 1
    assert output["unresolved_pagination"] == 1
    assert output["partial"] is True
    assert len(output["candidates"]) == 1


def test_approved_listing_tabs_discover_more_accessible_offers():
    browser = make_browser(None)
    browser._open_portal = AsyncMock()
    listing = "https://empresa.co.computrabajo.com/Company/Offers/Match?oi=" + "B" * 32
    browser._evaluate = AsyncMock(side_effect=[
        directory_page(tabs=["finalizadas"]),
        directory_page(tabs=["finalizadas"]),   # base before switching tab
        {"clicked": True},
        directory_page(offers=[listing]),       # after switching tab
        directory_page(candidates=[directory_candidate("A")]),
    ])
    output = asyncio.run(browser._discover_all_candidates_async(max_pages=10))
    assert output["pages"] == 3
    assert output["offers_found"] == 1
    assert len(output["candidates"]) == 1
    assert output["partial"] is False


def test_duplicate_candidates_across_multiple_lists_are_returned_once():
    browser = make_browser(None)
    browser._open_portal = AsyncMock()
    first = "https://empresa.co.computrabajo.com/Company/Offers/Match?oi=" + "B" * 32
    second = "https://empresa.co.computrabajo.com/Company/Offers/Match?oi=" + "C" * 32
    browser._evaluate = AsyncMock(side_effect=[
        directory_page(offers=[first, second]),
        directory_page(candidates=[directory_candidate("A")]),
        directory_page(candidates=[directory_candidate("A")]),
    ])
    output = asyncio.run(browser._discover_all_candidates_async(max_pages=10))
    assert output["offers_found"] == 2
    assert output["candidate_pages"] == 2
    assert output["pages"] == 3
    assert len(output["candidates"]) == 1


def test_candidate_status_tabs_are_traversed_without_importing_vacancies():
    browser = make_browser(None)
    browser._open_portal = AsyncMock()
    listing = "https://empresa.co.computrabajo.com/Company/Offers/Match?oi=" + "B" * 32
    browser._evaluate = AsyncMock(side_effect=[
        directory_page(offers=[listing]),
        directory_page(candidates=[directory_candidate("A")],
                       tabs=["seleccionados (6)"], active_page="1"),
        directory_page(candidates=[directory_candidate("A")],
                       tabs=["seleccionados (6)"], active_page="1"),
        {"clicked": True},
        directory_page(candidates=[directory_candidate("C")],
                       active_page="1", active_tab="seleccionados (6)"),
    ])
    result = asyncio.run(browser._discover_all_candidates_async(max_pages=10))
    assert result["pages"] == 3
    assert result["candidate_pages"] == 2
    assert result["offers_found"] == 1
    assert {c["external_id"] for c in result["candidates"]} == {"A" * 32, "C" * 32}
    tab_script = browser._evaluate.await_args_list[3].args[1]
    assert "seleccionados (6)" in tab_script
    assert "/company/offers/match" in tab_script


def test_active_tab_change_is_new_page_even_when_both_statuses_empty():
    browser = make_browser(None)
    browser._open_portal = AsyncMock()
    base = directory_page(offers=[], tabs=["finalizadas"])
    browser._evaluate = AsyncMock(side_effect=[
        base,
        base,
        {"clicked": True},
        directory_page(active_tab="finalizadas"),
    ])
    # The root has no candidates, so a separate cancellation bypasses
    # the ordinary no-candidates exception; it still must scan both tabs.
    with pytest.raises(ValueError, match="COMPUTRABAJO_NO_CANDIDATES_DISCOVERED"):
        asyncio.run(browser._discover_all_candidates_async(max_pages=10))
    assert browser._open_portal.await_count == 2


def test_reported_applicant_count_marks_incomplete_listing():
    browser = make_browser(None)
    browser._open_portal = AsyncMock()
    listing = "https://empresa.co.computrabajo.com/Company/Offers/Match?oi=" + "B" * 32
    browser._evaluate = AsyncMock(side_effect=[
        directory_page(offers=[listing]),
        directory_page(candidates=[directory_candidate("A")], reported_received=547),
    ])
    output = asyncio.run(browser._discover_all_candidates_async(max_pages=10))
    assert output["pages"] == 2
    assert output["reported_received_total"] == 547
    assert output["discovered_with_reported_total"] == 1
    assert output["offers_with_missing_candidates"] == 1
    assert output["partial"] is True



def test_ajax_empty_intermediate_screen_does_not_skip_30_applicants():
    """The pager clears DOM links before the next batch of candidate cards loads."""
    browser = make_browser(None)
    browser._open_portal = AsyncMock()
    browser._evaluate = AsyncMock(side_effect=[
        directory_page(candidates=[directory_candidate("A")],
                       js_next=True, active_page="1"),
        {"clicked": True, "target_page": 2},
        # The page badge changes immediately, but its CV links are still loading.
        directory_page(candidates=[], active_page="2", js_next=True),
        directory_page(candidates=[directory_candidate("B")],
                       js_next=False, active_page="2"),
    ])
    output = asyncio.run(browser._discover_all_candidates_async(max_pages=20))
    assert output["pages"] == 2
    assert output["unresolved_pagination"] == 0
    assert output["partial"] is False
    assert {c["external_id"] for c in output["candidates"]} == {
        "A" * 32, "B" * 32,
    }


def test_ajax_page_that_never_populates_is_partial_not_counted():
    """Do not claim a blank transition page was synchronized."""
    browser = make_browser(None)
    browser._open_portal = AsyncMock()
    first = directory_page(candidates=[directory_candidate("A")],
                           active_page="1", js_next=True)
    blank = directory_page(candidates=[], active_page="2", js_next=True)
    browser._evaluate = AsyncMock(side_effect=[
        first, {"clicked": True, "target_page": 2}, *([blank] * 14),
    ])
    output = asyncio.run(browser._discover_all_candidates_async(max_pages=20))
    assert output["pages"] == 1
    assert output["unresolved_pagination"] == 1
    assert output["partial"] is True
    assert len(output["candidates"]) == 1
