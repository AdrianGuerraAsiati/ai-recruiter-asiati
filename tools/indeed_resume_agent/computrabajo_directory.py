"""Safe, candidate-only Computrabajo directory navigation contracts.

Scripts read the visible authenticated employer UI. They do not fetch privileged
endpoints, submit forms, create listings, or circumvent access restrictions.
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

HOST = "empresa.co.computrabajo.com"
OFFERS_PATH = "/company/offers"
CANDIDATES_PATH = "/company/offers/match"
DETAIL_PATH = "/company/matchcvdetail/matchdetail"
OFFERS_START = "https://empresa.co.computrabajo.com/Company/Offers"


def directory_url(raw: object) -> str | None:
    """Only allow known employer list and candidate-list HTTPS paths."""
    try:
        value = str(raw or "").strip()
        p = urlsplit(value)
        if p.scheme != "https" or p.hostname != HOST or p.username or p.password:
            return None
        if p.path.lower().rstrip("/") not in {OFFERS_PATH, CANDIDATES_PATH}:
            return None
        if p.port not in {None, 443}:
            return None
        return urlunsplit((p.scheme, p.netloc, p.path, p.query, ""))
    except ValueError:
        return None


def candidate_detail_url(raw: object, external_id: object) -> bool:
    """Check that a visible candidate URL carries its own validated ID."""
    from string import hexdigits

    try:
        p = urlsplit(str(raw or ""))
        candidate_id = str(external_id or "")
        if (
            p.scheme != "https" or p.hostname != HOST or
            p.username or p.password or p.port not in {None, 443} or
            p.path.lower() != DETAIL_PATH or
            not 16 <= len(candidate_id) <= 64 or
            any(c not in hexdigits for c in candidate_id)
        ):
            return False
        from urllib.parse import parse_qs
        return candidate_id.casefold() in [
            value.casefold() for value in parse_qs(p.query).get("ims", [])
        ]
    except ValueError:
        return False


# Distinguish direct links, JS-only next page, accessible filter tabs,
# and provider-side expired-offer blocks without collecting any personal data
# except links/names necessary to perform authorized candidate ingestion.
DIRECTORY_SCAN_JS = r"""(() => {
  const origin = 'https://empresa.co.computrabajo.com';
  const path = location.pathname.toLowerCase().replace(/\/$/, '');
  if (location.origin !== origin ||
      !['/company/offers', '/company/offers/match'].includes(path)) {
    return {error: 'COMPUTRABAJO_LOGIN_OR_LIST_REQUIRED'};
  }
  const text = (document.body?.innerText || '').toLowerCase();
  if (/su oferta de empleo ha vencido|oferta de empleo ha vencido|contratar una membresía/i.test(text)) {
    return {access_denied: 'OFFER_EXPIRED', candidates: [], offer_links: [],
            page_links: [], tabs_js: [], js_next: false};
  }
  const candidates = [], offerLinks = [], pageLinks = [], tabs = [];
  const candidateIds = new Set(), directOffers = new Set(), directPages = new Set();
  const pager = el => !!el.closest(
    '.pagination, .pager, [class*="pagination"], [class*="paginacion"], nav[aria-label*="age"], nav[aria-label*="ágina"]'
  );
  const nextControl = el => {
    const label = (el.getAttribute('aria-label') || el.getAttribute('title') ||
                   el.textContent || '').trim().toLowerCase();
    return el.rel === 'next' || /\b(siguiente|next)\b|^[›»→]+$/.test(label);
  };
  const tabName = el => (el.getAttribute('aria-label') || el.textContent || '')
    .toLowerCase().trim().replace(/\s+/g, ' ').slice(0, 75);
  const safeTab = name => path === '/company/offers/match'
    ? /^(recibid[oa]s|seleccionad[oa]s|finalistas?|descartad[oa]s|preseleccionad[oa]s|rechazad[oa]s|entrevistad[oa]s)(\s*\(\s*\d+\s*\))?$/i.test(name)
    : /^(todas?|activas?|inactivas?|finalizadas?|vencidas?|cerradas?|archivadas?|anteriores?|hist[oó]ricas?|publicadas?|pausadas?)(\b|$)/i.test(name);
  for (const a of document.querySelectorAll('a[href]')) {
    let url;
    try { url = new URL(a.getAttribute('href'), location.href); } catch (_) { continue; }
    if (url.origin !== origin) continue;
    const target = url.pathname.toLowerCase().replace(/\/$/, '');
    if (path === '/company/offers/match' &&
        target === '/company/matchcvdetail/matchdetail') {
      const id = url.searchParams.get('ims') || '';
      if (!/^[a-f0-9]{16,64}$/i.test(id) || candidateIds.has(id.toLowerCase())) continue;
      candidateIds.add(id.toLowerCase());
      const name = (a.querySelector('strong, b, h3, h4')?.textContent ||
        a.textContent || '').split('\n')[0].trim().slice(0, 180);
      candidates.push({external_id: id, candidate_name: name, detail_url: url.href});
    } else if (path === '/company/offers' &&
               target === '/company/offers/match' && url.searchParams.has('oi')) {
      if (!directOffers.has(url.href)) {
        directOffers.add(url.href);
        offerLinks.push(url.href);
      }
    } else if (target === path && url.href !== location.href &&
               (pager(a) || nextControl(a) || a.closest('[role="tab"], .nav-tabs, .tabs') ||
                (url.search && url.search !== location.search))) {
      if (!directPages.has(url.href)) {
        directPages.add(url.href);
        pageLinks.push(url.href);
      }
    }
  }
  for (const el of document.querySelectorAll('[role="tab"], .nav-tabs button, .nav-tabs a, .tabs button, .tabs a, [data-toggle="tab"], [data-bs-toggle="tab"]')) {
    const name = tabName(el);
    if (safeTab(name) && !el.disabled &&
        el.getAttribute('aria-selected') !== 'true' &&
        !el.classList.contains('active') && !tabs.includes(name)) {
      const href = el.getAttribute('href') || '';
      if (!href || href.startsWith('#') || href.toLowerCase().startsWith('javascript:')) tabs.push(name);
    }
  }
  const activeTab = [...document.querySelectorAll('[role="tab"][aria-selected="true"], .nav-tabs .active, .tabs .active, .tablist .active, [data-toggle="tab"].active')].map(tabName).find(safeTab) || '';
  const activePage = document.querySelector(
    '.pagination .active, .pager .active, [aria-current="page"]'
  )?.textContent?.trim().slice(0, 30) || '';
  const activeNumber = /^\d+$/.test(activePage) ? Number(activePage) : 0;
  let jsNext = false;
  for (const el of document.querySelectorAll('a, button')) {
    if (el.disabled || el.getAttribute('aria-disabled') === 'true' ||
        el.closest('[disabled]')) continue;
    const numericNext = pager(el) && activeNumber > 0 && /^\d+$/.test((el.textContent || '').trim())
      && Number((el.textContent || '').trim()) === activeNumber + 1;
    if ((!nextControl(el) && !numericNext) || !(pager(el) || el.rel === 'next')) continue;
    const href = el.getAttribute('href') || '';
    let url;
    try { url = new URL(href, location.href); } catch (_) { url = null; }
    if (!href || href.startsWith('#') || href.toLowerCase().startsWith('javascript:') ||
        (url && url.href === location.href)) jsNext = true;
  }
  const received = [...document.querySelectorAll(
    '[role="tab"], .nav-tabs a, .nav-tabs button, .tabs a, .tabs button, [data-toggle="tab"], [data-bs-toggle="tab"]'
  )].map(tabName).find(t => /^recibid[oa]s\s*\(\s*\d+\s*\)$/i.test(t));
  const reportedReceived = received ? Number(received.match(/\(\s*(\d+)\s*\)/)?.[1]) : null;
  return {candidates, offer_links: offerLinks, page_links: pageLinks,
          tabs_js: tabs, js_next: jsNext, active_page: activePage,
          active_tab: activeTab, reported_received: reportedReceived};
})()"""


NEXT_PAGE_JS = r"""(() => {
  const pathname = location.pathname.toLowerCase().replace(/\/$/, '');
  if (location.hostname !== 'empresa.co.computrabajo.com' ||
      !['/company/offers', '/company/offers/match'].includes(pathname))
    return {clicked: false};
  const pager = el => !!el.closest(
    '.pagination, .pager, [class*="pagination"], [class*="paginacion"], nav[aria-label*="age"], nav[aria-label*="ágina"]');
  const activePage = document.querySelector(
    '.pagination .active, .pager .active, [aria-current="page"]'
  )?.textContent?.trim() || '';
  const activeNumber = /^\d+$/.test(activePage) ? Number(activePage) : 0;
  for (const el of document.querySelectorAll('a, button')) {
    const label = (el.getAttribute('aria-label') || el.getAttribute('title') ||
                   el.textContent || '').trim().toLowerCase();
    const isNext = el.rel === 'next' || /\b(siguiente|next)\b|^[›»→]+$/.test(label)
      || (pager(el) && activeNumber > 0 && /^\d+$/.test(label)
          && Number(label) === activeNumber + 1);
    if (!isNext || !(pager(el) || el.rel === 'next') ||
        el.disabled || el.getAttribute('aria-disabled') === 'true') continue;
    const href = el.getAttribute('href') || '';
    let u = null;
    try { u = new URL(href, location.href); } catch (_) {}
    if (href && !href.startsWith('#') && !href.toLowerCase().startsWith('javascript:') &&
        u && u.href !== location.href) continue;
    el.click();
    return {clicked: true};
  }
  return {clicked: false};
})()"""


def tab_click_js(name: str, *, candidate_list: bool = False) -> str:
    """Click only known navigation tabs, never candidate state-changing actions."""
    import json

    if not isinstance(name, str) or len(name) > 75:
        raise ValueError("COMPUTRABAJO_INVALID_TAB")
    # Only the two read-only listing paths are permitted.
    path = CANDIDATES_PATH if candidate_list else OFFERS_PATH
    return r"""(() => {
      const key = """ + json.dumps(name) + r""";
      const expectedPath = """ + json.dumps(path) + r""";
      if (location.hostname !== 'empresa.co.computrabajo.com' ||
          location.pathname.toLowerCase().replace(/\/$/, '') !== expectedPath)
        return {clicked: false};
      const valid = n => expectedPath === '/company/offers/match'
        ? /^(recibid[oa]s|seleccionad[oa]s|finalistas?|descartad[oa]s|preseleccionad[oa]s|rechazad[oa]s|entrevistad[oa]s)(\s*\(\s*\d+\s*\))?$/i.test(n)
        : /^(todas?|activas?|inactivas?|finalizadas?|vencidas?|cerradas?|archivadas?|anteriores?|hist[oó]ricas?|publicadas?|pausadas?)(\b|$)/i.test(n);
      if (!valid(key)) return {clicked: false};
      for (const el of document.querySelectorAll('[role="tab"], .nav-tabs button, .nav-tabs a, .tabs button, .tabs a, [data-toggle="tab"], [data-bs-toggle="tab"]')) {
        const current = (el.getAttribute('aria-label') || el.textContent || '')
          .toLowerCase().trim().replace(/\s+/g, ' ').slice(0, 75);
        if (current === key && !el.disabled) {
          el.click();
          return {clicked: true};
        }
      }
      return {clicked: false};
    })()"""
