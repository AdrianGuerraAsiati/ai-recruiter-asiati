"""Unit contracts for bounded browser-only Computrabajo pagination."""

import pytest

from tools.indeed_resume_agent.computrabajo_directory import (
    DIRECTORY_SCAN_JS, NEXT_PAGE_JS, candidate_detail_url, directory_url,
    tab_click_js,
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


def test_candidate_status_click_contract_is_read_only_and_domain_scoped():
    for status in ("recibidos (547)", "seleccionados (6)", "descartados (65)"):
        expression = tab_click_js(status)
        assert status in expression
        assert "'/company/offers/match'" in expression
        assert ".click()" in expression
        assert "fetch(" not in expression
    assert "status_counts" in DIRECTORY_SCAN_JS
    assert "reported_total" in DIRECTORY_SCAN_JS
    assert "Number(current + 1)" in DIRECTORY_SCAN_JS
