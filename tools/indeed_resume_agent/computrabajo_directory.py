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
  const isClickable = el => !(
    el.disabled || el.getAttribute('aria-disabled') === 'true' ||
    el.closest('[disabled], [aria-disabled="true"]'));
  const pagerRoot = el => {
    const known = el.closest(
      '.pagination, .pager, [class*="pagin"], [id*="pagin"], [class*="paging"], [id*="paging"], [class*="pagebar"], [id*="pagebar"], nav[aria-label*="age"], nav[aria-label*="ágina"]'
    );
    if (known) return known;
    // Provider-specific pagers can have no semantic class. Recognize only
    // compact navigation groups of consecutive numbered links/buttons.
    let parent = el.parentElement;
    for (let depth = 0; parent && depth < 3; depth++, parent = parent.parentElement) {
      const members = [...parent.querySelectorAll('a,button,[role="button"]')];
      if (members.length < 3 || members.length > 20) continue;
      const numbers = [...new Set(members.map(m =>
        (m.textContent || '').trim()).filter(t => /^\d{1,4}$/.test(t)).map(Number))];
      if (numbers.length >= 3 && numbers.length <= 12 &&
          numbers.some(n => numbers.includes(n + 1))) return parent;
    }
    return null;
  };
  const pager = el => !!pagerRoot(el);
  const controlNumber = el => {
    const label = (el.textContent || '').trim();
    return /^\d{1,4}$/.test(label) ? Number(label) : 0;
  };
  const forwardArrow = el => {
    const meta = [el.getAttribute('aria-label'), el.title, el.rel,
      el.getAttribute('data-action'), el.className,
      ...[...el.querySelectorAll('i,svg,span')].map(n => n.getAttribute('class'))
    ].filter(x => typeof x === 'string').join(' ').toLowerCase();
    const label = (el.textContent || '').trim().toLowerCase();
    if (/\b(prev|previous|anterior|back|atr[aá]s|left|izquierda)\b|(^|[-_])(prev|left)([-_]|$)/i.test(meta))
      return false;
    return /\b(next|siguiente|right|derecha|forward)\b|(^|[-_])(next|right)([-_]|$)/i.test(meta) ||
      /^[›»→]+$/.test(label);
  };
  const activePageNumber = () => {
    const active = [...document.querySelectorAll(
      '.pagination .active, .pager .active, [class*="pagin"] .active, [class*="pagin"] .selected, [class*="pagin"] .current, [class*="paging"] .active, [class*="paging"] .current, [aria-current="page"]'
    )].find(el => pager(el) && /^\d{1,4}$/.test((el.textContent || '').trim()));
    return active ? Number(active.textContent.trim()) : 0;
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
               (pager(a) || forwardArrow(a) || a.closest('[role="tab"], .nav-tabs, .tabs') ||
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
        !el.classList.contains('active') &&
        !el.closest('li.active, [role="tab"][aria-selected="true"]') &&
        !tabs.includes(name)) {
      const href = el.getAttribute('href') || '';
      if (!href || href.startsWith('#') || href.toLowerCase().startsWith('javascript:')) tabs.push(name);
    }
  }
  const activeTab = [...document.querySelectorAll('[role="tab"][aria-selected="true"], .nav-tabs .active, .tabs .active, .tablist .active, [data-toggle="tab"].active')].map(tabName).find(safeTab) || '';
  const activeNumber = activePageNumber();
  const activePage = activeNumber ? String(activeNumber) : '';
  let jsNext = false;
  let pager_numbers = [];
  for (const el of document.querySelectorAll('a, button, [role="button"]')) {
    if (!pager(el) || !isClickable(el)) continue;
    const number = controlNumber(el);
    if (number) pager_numbers.push(number);
    const isNext = forwardArrow(el) ||
      (number > 0 && (activeNumber ? number > activeNumber : number >= 2));
    if (!isNext) continue;
    const href = el.getAttribute('href') || '';
    let url;
    try { url = new URL(href, location.href); } catch (_) { url = null; }
    if (!href || href.startsWith('#') || href.toLowerCase().startsWith('javascript:') ||
        (url && url.href === location.href)) jsNext = true;
  }
  pager_numbers = [...new Set(pager_numbers)].sort((a,b) => a-b);
  // Counts belong to the employer's *visible* status tabs. This does not
  // change statuses, fetch hidden data, or open restricted offer pages.
  const statusCounts = {};
  if (path === '/company/offers/match') {
    const tabElements = document.querySelectorAll(
      '[role="tab"], .nav-tabs a, .nav-tabs button, .tabs a, .tabs button, ' +
      '[class*="tab"] a, [class*="tab"] button, [data-toggle="tab"], [data-bs-toggle="tab"]'
    );
    for (const el of tabElements) {
      const label = tabName(el);
      const match = label.match(
        /^(recibid[oa]s|seleccionad[oa]s|finalistas?|descartad[oa]s)\s*\(\s*(\d{1,7})\s*\)$/i
      );
      if (!match) continue;
      const count = Number(match[2]);
      if (count <= 1000000) statusCounts[match[1]] = count;
    }
  }
  const reportedReceived = statusCounts.recibidos ?? statusCounts.recibidas ?? null;
  // Some offers display "618 inscritos" rather than a "total" tab.
  // Dots and commas here are thousands separators, not decimals.
  const declared = path === '/company/offers/match'
    ? text.match(/\b(\d[\d.,]{0,10})\s+(?:candidatos?\s+)?inscritos\b/i)
    : null;
  const rawTotal = declared?.[1] || '';
  const validTotal = /^\d{1,7}$/.test(rawTotal) ||
    /^\d{1,3}(?:[.,]\d{3})+$/.test(rawTotal);
  const value = validTotal ? Number(rawTotal.replace(/[.,]/g, '')) : null;
  const reportedTotal = value !== null && value <= 1000000 ? value : null;
  return {candidates, offer_links: offerLinks, page_links: pageLinks,
          tabs_js: tabs, js_next: jsNext, active_page: activePage,
          active_tab: activeTab, reported_received: reportedReceived,
          reported_total: reportedTotal, status_counts: statusCounts,
          pager_numbers: pager_numbers};
})()"""


NEXT_PAGE_JS = r"""(() => {
  const expectedFloor = __PAGE_FLOOR__;
  if (location.hostname !== 'empresa.co.computrabajo.com' ||
      !['/company/offers', '/company/offers/match'].includes(
        location.pathname.toLowerCase().replace(/\/$/, '')
      )) return {clicked: false};
  const isClickable = el => !(
    el.disabled || el.getAttribute('aria-disabled') === 'true' ||
    el.closest('[disabled], [aria-disabled="true"]'));
  const pagerRoot = el => {
    const known = el.closest(
      '.pagination, .pager, [class*="pagin"], [id*="pagin"], [class*="paging"], [id*="paging"], [class*="pagebar"], [id*="pagebar"], nav[aria-label*="age"], nav[aria-label*="ágina"]'
    );
    if (known) return known;
    // Provider-specific pagers can have no semantic class. Recognize only
    // compact navigation groups of consecutive numbered links/buttons.
    let parent = el.parentElement;
    for (let depth = 0; parent && depth < 3; depth++, parent = parent.parentElement) {
      const members = [...parent.querySelectorAll('a,button,[role="button"]')];
      if (members.length < 3 || members.length > 20) continue;
      const numbers = [...new Set(members.map(m =>
        (m.textContent || '').trim()).filter(t => /^\d{1,4}$/.test(t)).map(Number))];
      if (numbers.length >= 3 && numbers.length <= 12 &&
          numbers.some(n => numbers.includes(n + 1))) return parent;
    }
    return null;
  };
  const pager = el => !!pagerRoot(el);
  const controlNumber = el => {
    const label = (el.textContent || '').trim();
    return /^\d{1,4}$/.test(label) ? Number(label) : 0;
  };
  const forwardArrow = el => {
    const meta = [el.getAttribute('aria-label'), el.title, el.rel,
      el.getAttribute('data-action'), el.className,
      ...[...el.querySelectorAll('i,svg,span')].map(n => n.getAttribute('class'))
    ].filter(x => typeof x === 'string').join(' ').toLowerCase();
    const label = (el.textContent || '').trim().toLowerCase();
    if (/\b(prev|previous|anterior|back|atr[aá]s|left|izquierda)\b|(^|[-_])(prev|left)([-_]|$)/i.test(meta))
      return false;
    return /\b(next|siguiente|right|derecha|forward)\b|(^|[-_])(next|right)([-_]|$)/i.test(meta) ||
      /^[›»→]+$/.test(label);
  };
  const activePageNumber = () => {
    const active = [...document.querySelectorAll(
      '.pagination .active, .pager .active, [class*="pagin"] .active, [class*="pagin"] .selected, [class*="pagin"] .current, [class*="paging"] .active, [class*="paging"] .current, [aria-current="page"]'
    )].find(el => pager(el) && /^\d{1,4}$/.test((el.textContent || '').trim()));
    return active ? Number(active.textContent.trim()) : 0;
  };

  const active = activePageNumber();
  const floor = Math.max(active, expectedFloor);
  const controls = [...document.querySelectorAll('a,button,[role="button"]')]
    .filter(el => pager(el) && isClickable(el));
  const hasLocalClick = el => {
    const href = el.getAttribute('href') || '';
    let url;
    try { url = new URL(href, location.href); } catch (_) { url = null; }
    return !href || href.startsWith('#') || /^javascript:/i.test(href) ||
      (url && url.href === location.href);
  };
  // Never jump from page 5 straight to page 7 when the provider only
  // moved the visible 1–5 numeric window to 6–10. Demand the *next*
  // sequential page; the Python driver will handle window-only arrows.
  const nextNumber = floor + 1;
  const pageTarget = controls.find(el =>
    controlNumber(el) === nextNumber && hasLocalClick(el));
  if (pageTarget) {
    pageTarget.click();
    return {clicked: true, target_page: nextNumber};
  }
  // When the visible numeric window ends (e.g. pages 1–5), advance using
  // a *forward* caret, never the previous/back control.
  const forward = controls.find(el => forwardArrow(el) && hasLocalClick(el));
  if (forward) {
    forward.click();
    // Arrow may only reveal another group of numbers, not load a CV page.
    return {clicked: true, target_page: nextNumber, arrow: true};
  }
  return {clicked: false};
})()"""


def pagination_next_js(*, after_page: int = 0) -> str:
    """Create a guarded click expression with a monotonically advancing floor."""
    if not isinstance(after_page, int) or not 0 <= after_page <= 10000:
        raise ValueError("COMPUTRABAJO_INVALID_PAGE")
    return NEXT_PAGE_JS.replace("__PAGE_FLOOR__", str(after_page))


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
