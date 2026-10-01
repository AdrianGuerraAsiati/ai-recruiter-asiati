from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from tools.indeed_resume_agent import self_test


def test_browser_preflight_retries_once_with_fresh_profile(monkeypatch, tmp_path):
    calls = []

    async def fake_check(chrome, profile_dir):
        calls.append(Path(profile_dir))
        if len(calls) == 1:
            raise TimeoutError("cold start")
        return True

    monkeypatch.setattr(self_test, "_browser_use_check", fake_check)

    ok = asyncio.run(
        self_test._browser_use_check_with_retry(
            Path("chrome.exe"),
            tmp_path / "profiles",
            attempts=2,
        )
    )

    assert ok is True
    assert calls == [
        tmp_path / "profiles" / "attempt-1",
        tmp_path / "profiles" / "attempt-2",
    ]


def test_browser_preflight_fails_after_bounded_retries(monkeypatch, tmp_path):
    calls = 0

    async def fake_check(chrome, profile_dir):
        nonlocal calls
        calls += 1
        raise TimeoutError("still slow")

    monkeypatch.setattr(self_test, "_browser_use_check", fake_check)

    with pytest.raises(TimeoutError, match="still slow"):
        asyncio.run(
            self_test._browser_use_check_with_retry(
                Path("chrome.exe"),
                tmp_path / "profiles",
                attempts=2,
            )
        )

    assert calls == 2
