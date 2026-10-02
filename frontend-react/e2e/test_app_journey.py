"""Real-browser journey and accessibility/layout smoke tests for the SPA."""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlparse

import pytest
from playwright.sync_api import Page, Route, expect, sync_playwright


BASE_URL = os.getenv("FRONTEND_E2E_BASE_URL", "http://127.0.0.1:4173")
ARTIFACT_DIR = Path(__file__).resolve().parents[1] / "test-results" / "e2e"


PRINCIPAL = {
    "email": "admin@asiati.com.co",
    "roles": ["ADMIN"],
    "permissions": [
        "jobs.read",
        "jobs.manage",
        "candidates.read",
        "candidates.manage",
        "candidates.evaluate",
        "ranking.read",
        "ranking.recalculate",
        "employees.read",
        "training.read",
        "training.manage",
        "training.assign",
        "training.results.read",
        "profile.read_own",
    ],
    "profile": {
        "id": "admin-1",
        "first_name": "Katherine",
        "last_name": "Admin",
    },
}


def _json(route: Route, payload: object, status: int = 200) -> None:
    route.fulfill(
        status=status,
        content_type="application/json",
        body=json.dumps(payload),
    )


def _api_contract(route: Route) -> None:
    request = route.request
    parsed = urlparse(request.url)
    path = parsed.path
    query = parsed.query
    method = request.method.upper()

    if path == "/api/auth/refresh":
        _json(route, {"detail": "anonymous"}, status=401)
        return
    if path == "/api/auth/login" and method == "POST":
        _json(route, {"access_token": "browser-e2e-token"})
        return
    if path == "/api/auth/me":
        _json(route, PRINCIPAL)
        return
    if path == "/api/jobs":
        _json(route, [])
        return
    if path == "/api/candidates" and "page=" in query:
        _json(route, {"items": [], "total": 0, "pages": 0, "page": 1})
        return
    if path == "/api/candidates":
        _json(route, [])
        return
    if path == "/api/employees/summary":
        _json(
            route,
            {
                "employees_total": 2,
                "active": 2,
                "disabled": 0,
                "onboarding": {
                    "total": 1,
                    "pending": 0,
                    "in_progress": 1,
                    "completed": 0,
                    "completion_percent": 50,
                },
            },
        )
        return

    _json(
        route,
        {"detail": f"Unexpected E2E request: {method} {path}"},
        status=404,
    )


def _assert_accessible_controls(page: Page) -> None:
    issues = page.evaluate(
        """() => {
          const visible = (el) => {
            const style = getComputedStyle(el);
            return style.display !== "none"
              && style.visibility !== "hidden"
              && el.getClientRects().length > 0;
          };
          const labelText = (el) => {
            if (el.getAttribute("aria-label")) return el.getAttribute("aria-label").trim();
            if (el.getAttribute("aria-labelledby")) {
              return el.getAttribute("aria-labelledby")
                .split(/\\s+/)
                .map((id) => document.getElementById(id)?.textContent || "")
                .join(" ")
                .trim();
            }
            if (el.id) {
              const selector = 'label[for="' + CSS.escape(el.id) + '"]';
              const label = document.querySelector(selector);
              if (label?.textContent?.trim()) return label.textContent.trim();
            }
            const parentLabel = el.closest("label");
            return parentLabel?.textContent?.trim() || "";
          };

          const issues = [];
          const ids = [...document.querySelectorAll("[id]")]
            .map((el) => el.id)
            .filter(Boolean);
          const duplicates = ids.filter((id, index) => ids.indexOf(id) !== index);
          if (duplicates.length) {
            issues.push("duplicate ids: " + [...new Set(duplicates)].join(", "));
          }

          for (const control of document.querySelectorAll("input, select, textarea")) {
            if (!visible(control) || control.type === "hidden") continue;
            if (!labelText(control)) {
              issues.push("unlabelled " + control.tagName.toLowerCase() + "#" + (control.id || "(no-id)"));
            }
          }

          for (const button of document.querySelectorAll("button")) {
            if (!visible(button)) continue;
            const name = (
              button.getAttribute("aria-label")
              || button.textContent
              || button.getAttribute("title")
              || ""
            ).trim();
            if (!name) issues.push("button without accessible name");
          }

          for (const image of document.querySelectorAll("img")) {
            if (visible(image) && !image.hasAttribute("alt")) {
              issues.push("img without alt: " + image.src);
            }
          }
          return issues;
        }"""
    )
    assert issues == []


def _assert_layout_fits_viewport(page: Page) -> None:
    overflow = page.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow <= 1


@pytest.fixture
def browser_page() -> Page:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        try:
            yield page
        finally:
            browser.close()


@pytest.fixture
def app_page(browser_page: Page) -> Page:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    browser_page.route("**/api/**", _api_contract)
    return browser_page


def _login(page: Page) -> None:
    page.goto(f"{BASE_URL}/login")
    expect(page.get_by_role("heading", name="Bienvenido", exact=True)).to_be_visible()
    page.get_by_label("Usuario").fill("admin@asiati.com.co")
    page.get_by_label("Contraseña").fill("secret-password")
    page.get_by_role("button", name="Iniciar sesión").click()
    expect(page.get_by_text("Vacantes activas")).to_be_visible()


def test_login_dashboard_and_candidate_directory_in_chromium(app_page: Page) -> None:
    page = app_page
    _login(page)

    expect(page.get_by_text("Onboarding del equipo")).to_be_visible()
    _assert_accessible_controls(page)
    _assert_layout_fits_viewport(page)
    page.screenshot(path=str(ARTIFACT_DIR / "dashboard-desktop.png"), full_page=True)

    page.get_by_role("link", name="Candidatos").click()
    expect(
        page.locator(".ui-page-header").get_by_role(
            "heading",
            name="Candidatos",
            exact=True,
        )
    ).to_be_visible()
    expect(page.get_by_text("Aún no hay candidatos registrados")).to_be_visible()
    _assert_accessible_controls(page)
    _assert_layout_fits_viewport(page)


def test_mobile_navigation_has_no_horizontal_overflow(app_page: Page) -> None:
    page = app_page
    page.set_viewport_size({"width": 390, "height": 844})
    _login(page)

    _assert_layout_fits_viewport(page)
    _assert_accessible_controls(page)
    page.screenshot(path=str(ARTIFACT_DIR / "dashboard-mobile.png"), full_page=True)
