from pathlib import Path

import pytest

from tools.indeed_resume_agent import browser_runtime


class _FakeProcess:
    def __init__(self, name: str, cmdline: list[str]):
        self.info = {"name": name, "cmdline": cmdline}


def test_resolve_browser_executable_prefers_path_lookup(monkeypatch):
    monkeypatch.setattr(
        browser_runtime.shutil,
        "which",
        lambda name: "/opt/google/chrome" if name == "chrome" else None,
    )

    assert browser_runtime.resolve_browser_executable("chrome") == "/opt/google/chrome"


def test_resolve_browser_executable_uses_windows_install_root(monkeypatch, tmp_path):
    executable = tmp_path / "Microsoft" / "Edge" / "Application" / "msedge.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"edge")

    monkeypatch.setattr(browser_runtime.shutil, "which", lambda _name: None)
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path))
    monkeypatch.delenv("PROGRAMFILES(X86)", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)

    assert browser_runtime.resolve_browser_executable("edge") == str(executable)


def test_resolve_browser_executable_rejects_unknown_browser():
    with pytest.raises(RuntimeError, match="Navegador no soportado"):
        browser_runtime.resolve_browser_executable("firefox")


def test_manual_browser_process_exists_matches_profile_owner(monkeypatch, tmp_path):
    profile_dir = tmp_path / "profile"
    processes = [
        _FakeProcess("chrome.exe", ["chrome.exe", "--type=renderer", f"--user-data-dir={profile_dir}"]),
        _FakeProcess("chrome.exe", ["chrome.exe", f'--user-data-dir="{profile_dir}"']),
    ]
    monkeypatch.setattr(browser_runtime.psutil, "process_iter", lambda _attrs: processes)

    assert browser_runtime.manual_browser_process_exists(
        Path(profile_dir),
        process_name="chrome.exe",
    )


def test_manual_browser_process_exists_ignores_other_profiles(monkeypatch, tmp_path):
    profile_dir = tmp_path / "profile"
    other_profile = tmp_path / "other"
    processes = [
        _FakeProcess("chrome.exe", ["chrome.exe", f"--user-data-dir={other_profile}"]),
        _FakeProcess("msedge.exe", ["msedge.exe", f"--user-data-dir={profile_dir}"]),
    ]
    monkeypatch.setattr(browser_runtime.psutil, "process_iter", lambda _attrs: processes)

    assert not browser_runtime.manual_browser_process_exists(
        profile_dir,
        process_name="chrome.exe",
    )
