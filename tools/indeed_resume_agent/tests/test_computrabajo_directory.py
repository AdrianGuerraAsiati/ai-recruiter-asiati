"""Unit contracts for bounded browser-only Computrabajo pagination."""

import pytest

from tools.indeed_resume_agent.computrabajo_directory import (
    DIRECTORY_SCAN_JS, NEXT_PAGE_JS, candidate_detail_url, directory_url,
    pagination_next_js, tab_click_js,
)


@pytest.mark.parametrize("url", [
    "https://fake.com/Company/Offers",
    "http://empresa.co.computrabajo.com/Company/Offers",
    "https://empresa.co.computrabajo.com.evil.com/Company/Offers",
    "https://empresa.co.computrabajo.com/Company/Offers/Publish",
    "https://empresa.co.computrabajo.com/Company/MatchCvDetail/MatchDetail?ims=123",
    "https://guest:password@empresa.co.computrabajo.com/Company/Offers",
])
def test_directory_urls_disallow_non_listing_and_foreign_origin(url):
    assert directory_url(url) is None


def test_directory_urls_accept_only_candidate_and_offer_lists():
    assert directory_url("https://empresa.co.computrabajo.com/Company/Offers?page=2")
    assert directory_url("https://empresa.co.computrabajo.com/Company/Offers/Match?oi=abc")


def test_candidate_url_requires_matching_identity_and_valid_path():
    external_id = "A" * 32
    detail = (
        "https://empresa.co.computrabajo.com/Company/MatchCvDetail/MatchDetail?ims="
        + external_id
    )
    assert candidate_detail_url(detail, external_id)
    assert not candidate_detail_url(detail, "B" * 32)
    assert not candidate_detail_url(detail.replace("computrabajo.com", "evil.com"), external_id)


def test_js_navigation_never_submits_or_bypasses_access():
    assert "OFFER_EXPIRED" in DIRECTORY_SCAN_JS
    assert "js_next" in DIRECTORY_SCAN_JS
    assert "offer_links" in DIRECTORY_SCAN_JS
    assert "candidate_name" in DIRECTORY_SCAN_JS
    assert ".click()" in NEXT_PAGE_JS
    assert "fetch(" not in DIRECTORY_SCAN_JS
    assert "fetch(" not in NEXT_PAGE_JS


def test_tab_expression_restricts_to_known_status_filters():
    expression = tab_click_js("finalizadas")
    assert "finalizadas" in expression
    assert "clicked" in expression
    with pytest.raises(ValueError, match="COMPUTRABAJO_INVALID_TAB"):
        tab_click_js("x" * 76)


def test_candidate_tabs_have_a_read_only_scope_distinct_from_offer_tabs():
    candidate_tab = tab_click_js("recibidos (547)", candidate_list=True)
    assert "/company/offers/match" in candidate_tab
    assert "recibid" in candidate_tab
    assert ".click()" in candidate_tab
    assert "fetch(" not in candidate_tab
    assert "fetch(" not in DIRECTORY_SCAN_JS
    assert "recibid" in DIRECTORY_SCAN_JS
    assert "seleccionad" in DIRECTORY_SCAN_JS


def test_numeric_js_pagination_next_page_is_supported():
    assert "pager_numbers" in DIRECTORY_SCAN_JS
    assert "pagerRoot" in DIRECTORY_SCAN_JS
    assert "pagerRoot" in NEXT_PAGE_JS
    assert "forwardArrow" in NEXT_PAGE_JS
    assert "expectedFloor" in NEXT_PAGE_JS
    assert "target_page" in NEXT_PAGE_JS
    assert "const expectedFloor = 5;" in pagination_next_js(after_page=5)
    assert "const expectedFloor = __PAGE_FLOOR__" in NEXT_PAGE_JS
    with pytest.raises(ValueError, match="COMPUTRABAJO_INVALID_PAGE"):
        pagination_next_js(after_page=-1)


def test_scan_exposes_authorized_count_without_fetching_hidden_profiles():
    assert "reported_total: reportedTotal" in DIRECTORY_SCAN_JS
    assert "status_counts: statusCounts" in DIRECTORY_SCAN_JS
    assert "candidatos?" in DIRECTORY_SCAN_JS
    assert "inscritos" in DIRECTORY_SCAN_JS
    assert "statusCounts" in DIRECTORY_SCAN_JS
    assert "fetch(" not in DIRECTORY_SCAN_JS
    assert "window.open(" not in DIRECTORY_SCAN_JS
