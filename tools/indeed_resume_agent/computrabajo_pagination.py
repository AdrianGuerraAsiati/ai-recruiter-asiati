"""Read-only applicant enumeration across accessible Computrabajo status tabs.

The only browser interactions are choosing status tabs and pagination controls.
No applicant state, hiring stage, or employer offer is changed.
"""
from __future__ import annotations

import asyncio
import json
import re
from string import hexdigits
from urllib.parse import urlparse

STATUSES = ("recibidos", "seleccionados", "finalistas", "descartados")
HOST = "empresa.co.computrabajo.com"

SCAN = r"""(() => {
  if (location.hostname !== 'empresa.co.computrabajo.com' ||
      location.pathname.toLowerCase().replace(/\/$/, '') !== '/company/offers/match')
    return {error:'COMPUTRABAJO_LIST_REQUIRED'};
  const body = (document.body?.innerText || '').toLowerCase();
  if (/su oferta de empleo ha vencido|oferta de empleo ha vencido|contratar una membresía/i.test(body))
    return {error:'COMPUTRABAJO_OFFER_EXPIRED_ACCESS_DENIED'};
  const statuses = ['recibidos','seleccionados','finalistas','descartados'];
  const label = el => (el.innerText || el.textContent || '')
    .replace(/\s+/g,' ').trim().toLowerCase();
  const controls = [...document.querySelectorAll('a,button,[role="tab"]')];
  const available=[], counts={};
  let active='';
  for (const el of controls) {
    const title=label(el);
    const state=statuses.find(s=>title===s ||
      new RegExp('^'+s+'\\s*\\(\\s*\\d+\\s*\\)$','i').test(title));
    if (!state || available.includes(state)) continue;
    available.push(state);
    const number=title.match(/\(\s*(\d+)\s*\)/);
    if (number) counts[state]=Number(number[1]);
    if (el.matches('.active,.selected,[aria-selected="true"]') ||
        el.closest('.active,.selected,.current,[aria-selected="true"]')) active=state;
  }
  const candidates=[], seen=new Set();
  for (const a of document.querySelectorAll('a[href*="/MatchCvDetail/MatchDetail"]')) {
    let u;
    try { u=new URL(a.href,location.href); } catch (_) { continue; }
    const id=u.searchParams.get('ims')||'';
    if (u.origin!==location.origin ||
        u.pathname.toLowerCase()!=='/company/matchcvdetail/matchdetail' ||
        !/^[a-f0-9]{16,64}$/i.test(id) || seen.has(id)) continue;
    seen.add(id);
    const name=(a.querySelector('strong,b,h3,h4')?.textContent ||
                a.textContent || '').trim().slice(0,180);
    candidates.push({external_id:id,candidate_name:name,detail_url:u.href});
  }
  const activePage=document.querySelector(
    '.pagination .active,.pager .active,[class*="pagin"] .active,[aria-current="page"]');
  const current=(activePage?.textContent||'').trim();
  const pageNumber=/^\d+$/.test(current)?Number(current):0;
  const next=[...document.querySelectorAll('a,button')].some(el=>{
    const container=el.closest('.pagination,.pager,[class*="pagin"],nav[aria-label]');
    const t=[label(el),el.getAttribute('aria-label')||'',el.title||'']
      .join(' ').toLowerCase();
    return !!container && !el.disabled &&
      el.getAttribute('aria-disabled')!=='true' &&
      !el.closest('.disabled,[aria-disabled="true"]') &&
      (/siguiente|next|^\s*[›»>]\s*$/.test(t) ||
       el.rel?.toLowerCase()==='next' ||
       (pageNumber>0 && label(el)===String(pageNumber+1)));
  });
  const total=body.match(/(\d{1,7})\s+candidatos inscritos/);
  return {candidates,statuses:available,counts,active_status:active,
    next,reported_total:total?Number(total[1]):null,
    signature:[location.href,active,current,
      candidates.map(c=>c.external_id).join(',')].join('|')};
})()"""

CLICK = r"""(() => {
  if (location.hostname !== 'empresa.co.computrabajo.com' ||
      location.pathname.toLowerCase().replace(/\/$/, '') !== '/company/offers/match')
    return false;
  const kind=KIND, desired=STATUS;
  const label=el=>(el.innerText||el.textContent||'')
    .replace(/\s+/g,' ').trim().toLowerCase();
  const activePage=document.querySelector(
    '.pagination .active,.pager .active,[class*="pagin"] .active,[aria-current="page"]');
  const current=(activePage?.textContent||'').trim();
  const n=/^\d+$/.test(current)?Number(current):0;
  const matches=[...document.querySelectorAll('a,button,[role="tab"]')]
    .filter(el=>{
      if (el.disabled || el.getAttribute('aria-disabled')==='true' ||
          el.closest('.disabled,[aria-disabled="true"]')) return false;
      if (kind==='status') {
        const t=label(el);
        return t===desired ||
          new RegExp('^'+desired+'\\s*\\(\\s*\\d+\\s*\\)$','i').test(t);
      }
      const c=el.closest('.pagination,.pager,[class*="pagin"],nav[aria-label]');
      const t=[label(el),el.getAttribute('aria-label')||'',el.title||'']
        .join(' ').toLowerCase();
      return !!c && (/siguiente|next|^\s*[›»>]\s*$/.test(t) ||
        el.rel?.toLowerCase()==='next' ||
        (n>0 && label(el)===String(n+1)));
    });
  const chosen=matches[0];
  if (!chosen) return false;
  const href=(chosen.getAttribute('href')||'').trim();
  if (href && href!=='#' && !/^javascript:void\(0\);?$/i.test(href)) {
    let u;
    try { u=new URL(href,location.href); } catch (_) { return false; }
    if (u.origin!==location.origin ||
        u.pathname.toLowerCase().replace(/\/$/,'')!=='/company/offers/match')
      return false;
  }
  chosen.click();
  return true;
})()"""


async def _snapshot(browser, cdp):
    value = await browser._evaluate(cdp, SCAN)
    if not isinstance(value, dict):
        raise RuntimeError("COMPUTRABAJO_LIST_INVALID")
    return value


async def _click(browser, cdp, kind, status=""):
    if kind not in ("status", "next"):
        return False
    if kind == "status" and status not in STATUSES:
        return False
    expression = CLICK.replace("KIND", json.dumps(kind)).replace(
        "STATUS", json.dumps(status)
    )
    return bool(await browser._evaluate(cdp, expression))


async def _changed(browser, cdp, before):
    for _ in range(18):
        await asyncio.sleep(0.4)
        try:
            page = await _snapshot(browser, cdp)
        except Exception:
            continue  # Navigation may briefly invalidate the document context.
        if page.get("error") or page.get("signature") != before:
            return page
    return None


def _candidate_valid(item):
    if not isinstance(item, dict):
        return False
    cid = str(item.get("external_id") or "")
    u = urlparse(str(item.get("detail_url") or ""))
    return (16 <= len(cid) <= 64 and
            all(c in hexdigits for c in cid) and
            u.scheme == "https" and u.hostname == HOST and
            u.path.casefold() == "/company/matchcvdetail/matchdetail")


async def collect_offer_applicants(browser, url, *,
                                   max_pages=500, stop_requested=None):
    """Scan authorized applicant tabs/pages with loop and coverage guards."""
    if max_pages < 1:
        return dict(candidates=[],pages=0,partial=True,blocked=False,expected=0)
    await browser._open_portal(url)
    cdp = await browser._ensure_started()
    first = await _snapshot(browser, cdp)
    if first.get("error") == "COMPUTRABAJO_OFFER_EXPIRED_ACCESS_DENIED":
        return dict(candidates=[],pages=1,partial=True,blocked=True,expected=0)
    if first.get("error"):
        raise ValueError(first["error"])
    counts = first.get("counts") or {}
    available = first.get("statuses") or []
    statuses = [s for s in STATUSES if s in available]
    if not statuses:
        statuses = [first.get("active_status") or "recibidos"]
    expected = sum(int(counts.get(s) or 0) for s in statuses)
    total = first.get("reported_total")
    partial = (len(statuses) < 4 or
               any(s not in counts for s in statuses) or
               (isinstance(total,int) and expected < total))
    results = {}
    pages = 0
    for status in statuses:
        if stop_requested and stop_requested():
            partial=True
            break
        if pages >= max_pages:
            partial=True
            break
        if counts.get(status) == 0:
            continue  # The provider reports an empty candidate status.
        await browser._open_portal(url)
        cdp = await browser._ensure_started()
        current = await _snapshot(browser, cdp)
        if current.get("error"):
            partial=True
            continue
        if status != (current.get("active_status") or "recibidos"):
            before = current.get("signature", "")
            if not await _click(browser, cdp, "status", status):
                partial=True
                continue
            current = await _changed(browser, cdp, before)
            if not current or current.get("error"):
                partial=True
                continue
        visited = set()
        while pages < max_pages:
            if stop_requested and stop_requested():
                partial=True
                break
            if not isinstance(current,dict) or current.get("error"):
                partial=True
                break
            signature = str(current.get("signature") or "")
            if signature in visited:
                partial=True
                break
            visited.add(signature)
            pages += 1
            for candidate in current.get("candidates") or []:
                if _candidate_valid(candidate):
                    results.setdefault(candidate["external_id"].casefold(),candidate)
            if not current.get("next"):
                break
            if pages >= max_pages:
                partial=True
                break
            if not await _click(browser, cdp, "next"):
                partial=True
                break
            current = await _changed(browser, cdp, signature)
            if not current or current.get("error"):
                partial=True
                break
    if expected and len(results)<expected:
        partial=True
    return dict(candidates=list(results.values()),pages=pages,
                expected=expected,partial=partial,blocked=False)
