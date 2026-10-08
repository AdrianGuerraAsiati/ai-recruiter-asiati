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
