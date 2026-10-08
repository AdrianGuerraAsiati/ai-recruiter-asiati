"""Browser E2E regression: recently integrated recruitment routes.

These checks never authenticate or mutate production data. They run against
the Vite preview started by scripts/run-frontend-e2e.sh in CI.
"""
import os

import pytest
from playwright.sync_api import sync_playwright


BASE_URL = os.environ.get("FRONTEND_E2E_BASE_URL", "http://127.0.0.1:4173")


@pytest.mark.parametrize("route", [
    "/candidates",
    "/candidates/test-candidate",
    "/ranking",
    "/psychotechnical",
    "/employees",
])
def test_integrated_recruitment_routes_require_authentication(route):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(f"{BASE_URL}{route}", wait_until="domcontentloaded")
            page.wait_for_url("**/login", timeout=15000)
            assert page.url.endswith("/login")
        finally:
            browser.close()


def test_public_psychotechnical_link_is_not_redirected_to_login():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.route("**/api/public/psychotechnical/**", lambda route: route.fulfill(
                status=404,
                content_type="application/json",
                body='{"detail":"Prueba no encontrada"}',
            ))
            page.goto(f"{BASE_URL}/psychotechnical/take/nonexistent-e2e-token", wait_until="domcontentloaded")
            page.wait_for_timeout(500)
            assert "/psychotechnical/take/" in page.url
            assert not page.url.endswith("/login")
        finally:
            browser.close()
