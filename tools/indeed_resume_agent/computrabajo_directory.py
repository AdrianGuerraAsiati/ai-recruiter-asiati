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
  const sameDirectory = p => ['/company/offers', '/company/offers/match'].includes(p);
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
  const offerTab = name => /^(todas?|activas?|inactivas?|finalizadas?|vencidas?|cerradas?|archivadas?|anteriores?|hist[oó]ricas?|publicadas?|pausadas?)(\b|$)/i.test(name);
  const candidateTab = name => /^(recibidos|seleccionados|finalistas|descartados)\s*(\(\s*\d+\s*\))?$/i.test(name);
  const safeTab = name => path === '/company/offers' ? offerTab(name) : candidateTab(name);
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
  for (const el of document.querySelectorAll('[role="tab"], .nav-tabs button, .nav-tabs a, .tabs button, .tabs a, [class*="tab"] a, [class*="tab"] button, [data-toggle="tab"], [data-bs-toggle="tab"]')) {
    const name = tabName(el);
    if (safeTab(name) && !el.disabled &&
        el.getAttribute('aria-selected') !== 'true' &&
        !el.classList.contains('active') &&
        !el.closest('.active,.selected,.current,[aria-selected="true"]') &&
        !tabs.includes(name)) {
      const href = el.getAttribute('href') || '';
      if (!href || href.startsWith('#') || href.toLowerCase().startsWith('javascript:')) tabs.push(name);
    }
  }
  let jsNext = false;
  for (const el of document.querySelectorAll('a, button')) {
    if (el.disabled || el.getAttribute('aria-disabled') === 'true' ||
        el.closest('[disabled]')) continue;
    if (!nextControl(el) || !(pager(el) || el.rel === 'next')) continue;
    const href = el.getAttribute('href') || '';
    let url;
    try { url = new URL(href, location.href); } catch (_) { url = null; }
    if (!href || href.startsWith('#') || href.toLowerCase().startsWith('javascript:') ||
        (url && url.href === location.href)) jsNext = true;
  }
  const activePage = document.querySelector(
    '.pagination .active, .pager .active, [aria-current="page"]'
  )?.textContent?.trim().slice(0, 30) || '';
  const statusCounts = {};
  if (path === '/company/offers/match') {
    for (const el of document.querySelectorAll('a,button,[role="tab"],[class*="tab"]')) {
      const name = tabName(el);
      const found = name.match(/^(recibidos|seleccionados|finalistas|descartados)\s*\(\s*(\d+)\s*\)$/);
      if (found) statusCounts[found[1]] = Number(found[2]);
    }
  }
  const totalMatch = text.match(/(\d{1,7})\s+candidatos inscritos/);
  return {candidates, offer_links: offerLinks, page_links: pageLinks,
          tabs_js: tabs, js_next: jsNext, active_page: activePage,
          status_counts: statusCounts,
          reported_total: totalMatch ? Number(totalMatch[1]) : null};
})()"""


NEXT_PAGE_JS = r"""(() => {
  const pathname = location.pathname.toLowerCase().replace(/\/$/, '');
  if (location.hostname !== 'empresa.co.computrabajo.com' ||
      !['/company/offers', '/company/offers/match'].includes(pathname))
    return {clicked: false};
  const pager = el => !!el.closest(
    '.pagination, .pager, [class*="pagination"], [class*="paginacion"], nav[aria-label*="age"], nav[aria-label*="ágina"]');
  for (const el of document.querySelectorAll('a, button')) {
    const label = (el.getAttribute('aria-label') || el.getAttribute('title') ||
                   el.textContent || '').trim().toLowerCase();
    const isNext = el.rel === 'next' || /\b(siguiente|next)\b|^[›»→]+$/.test(label);
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


def tab_click_js(name: str) -> str:
    """Build a tab-click expression with safely JSON-encoded label text."""
    import json
    if not isinstance(name, str) or len(name) > 75:
        raise ValueError("COMPUTRABAJO_INVALID_TAB")
    return r"""(() => {
      const key = """ + json.dumps(name) + r""";
      if (location.hostname !== 'empresa.co.computrabajo.com')
        return {clicked: false};
      const path = location.pathname.toLowerCase().replace(/\/$/, '');
      if (!['/company/offers','/company/offers/match'].includes(path))
        return {clicked: false};
      const offerTab = n => /^(todas?|activas?|inactivas?|finalizadas?|vencidas?|cerradas?|archivadas?|anteriores?|hist[oó]ricas?|publicadas?|pausadas?)(\b|$)/i.test(n);
      const candidateTab = n => /^(recibidos|seleccionados|finalistas|descartados)\s*(\(\s*\d+\s*\))?$/i.test(n);
      const valid = n => path === '/company/offers' ? offerTab(n) : candidateTab(n);
      if (!valid(key)) return {clicked: false};
      for (const el of document.querySelectorAll('[role="tab"], .nav-tabs button, .nav-tabs a, .tabs button, .tabs a, [class*="tab"] a, [class*="tab"] button, [data-toggle="tab"], [data-bs-toggle="tab"]')) {
        const name = (el.getAttribute('aria-label') || el.textContent || '')
          .toLowerCase().trim().replace(/\s+/g, ' ').slice(0, 75);
        if (name === key && !el.disabled) {
          el.click();
          return {clicked: true};
        }
      }
      return {clicked: false};
    })()"""
