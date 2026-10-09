"""Browser contract for five-number pagination windows, based on UI structure.

Synthetic candidate IDs only; no external Computrabajo request or credentials.
"""

from __future__ import annotations

import pytest

from tools.indeed_resume_agent.computrabajo_directory import (
    DIRECTORY_SCAN_JS,
    NEXT_PAGE_JS,
    pagination_next_js,
)

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

PAGE = r"""
<!doctype html><html><body>
  <div id="candidate-list"></div>
  <div id="navigation"></div>
  <script>
  const total = 547, perPage = 30;
  let currentPage = 1;
  function render(page) {
    currentPage = page;
    const list = document.getElementById('candidate-list');
    const start = (page - 1) * perPage;
    list.innerHTML = Array.from({length: Math.min(perPage, total - start)}, (_, i) => {
      const id = (start + i + 1).toString(16).padStart(32, '0');
      return '<a href="/Company/MatchCvDetail/MatchDetail?ims=' + id + '">Candidate ' + id + '</a>';
    }).join('');
    const pages = document.getElementById('navigation');
    const first = Math.floor((page - 1) / 5) * 5 + 1;
    const last = Math.min(first + 4, Math.ceil(total / perPage));
    let html = '';
    if (first > 1) html += '<button type="button" onclick="render(' + (first - 1) + ')">' +
      '<i class="fa fa-angle-left"></i></button>';
    for (let n = first; n <= last; n++) {
      html += '<a href="#" ' + (n === page ? 'aria-current="page"' : '') +
        ' onclick="render(' + n + ');return false">' + n + '</a>';
    }
    if (last < Math.ceil(total / perPage))
      html += '<button type="button" onclick="render(' + (last + 1) + ')">' +
        '<i class="fa fa-chevron-right"></i></button>';
    pages.innerHTML = html;
  }
  render(1);
  </script>
</body></html>"""


def test_grouped_numeric_pagination_reaches_all_547_authorized_candidates():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.route(
                "https://empresa.co.computrabajo.com/**",
                lambda route: route.fulfill(status=200, content_type="text/html", body=PAGE),
            )
            page.goto("https://empresa.co.computrabajo.com/Company/Offers/Match?oi=" + "A" * 32)
            seen = set()
            floor = 1
            pages = 0
            while True:
                result = page.evaluate(DIRECTORY_SCAN_JS)
                assert result.get("error") is None
                for item in result["candidates"]:
                    seen.add(item["external_id"])
                pages += 1
                if not result["js_next"]:
                    break
                click = page.evaluate(pagination_next_js(after_page=floor))
                assert click["clicked"], (pages, result["pager_numbers"], result["active_page"])
                floor = click["target_page"]
                assert pages < 25, "Pagination must not loop indefinitely"
            assert pages == 19
            assert len(seen) == 547
            assert floor == 19
            assert "target_page" in NEXT_PAGE_JS
        finally:
            browser.close()


def test_only_forward_arrow_is_clicked_at_page_window_boundary():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.route(
                "https://empresa.co.computrabajo.com/**",
                lambda route: route.fulfill(status=200, content_type="text/html", body=PAGE),
            )
            page.goto("https://empresa.co.computrabajo.com/Company/Offers/Match?oi=" + "A" * 32)
            page.evaluate("render(5)")
            result = page.evaluate(DIRECTORY_SCAN_JS)
            assert result["active_page"] == "5"
            assert result["js_next"] is True
            clicked = page.evaluate(pagination_next_js(after_page=5))
            assert clicked == {"clicked": True, "target_page": 6, "arrow": True}
            assert page.evaluate("currentPage") == 6
            page.evaluate("render(19)")
            assert page.evaluate(DIRECTORY_SCAN_JS)["js_next"] is False
            assert page.evaluate(pagination_next_js(after_page=19)) == {"clicked": False}
            assert page.evaluate("currentPage") == 19
        finally:
            browser.close()
