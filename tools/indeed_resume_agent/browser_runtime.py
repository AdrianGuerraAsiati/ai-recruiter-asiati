from __future__ import annotations

import os
import shutil
from pathlib import Path

import psutil


def manual_browser_process_exists(
    profile_dir: Path,
    *,
    process_name: str,
) -> bool:
    """Return True when the dedicated profile is owned by the selected browser."""
    target = os.path.normcase(os.path.normpath(str(profile_dir)))
    expected_process = str(process_name or "").casefold()
    for process in psutil.process_iter(["name", "cmdline"]):
        try:
            info = process.info
            if str(info.get("name") or "").casefold() != expected_process:
                continue
            args = [str(value) for value in (info.get("cmdline") or [])]
            if any(arg.startswith("--type=") for arg in args):
                continue
            for arg in args:
                if not arg.casefold().startswith("--user-data-dir="):
                    continue
                value = arg.split("=", 1)[1].strip().strip('"')
                candidate = os.path.normcase(os.path.normpath(value))
                if candidate == target:
                    return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return False


def resolve_browser_executable(browser_name: str) -> str:
    browser = str(browser_name or "").strip().casefold()
    if browser == "chrome":
        executable_name = "chrome.exe"
        shutil_names = ("chrome", "chrome.exe")
        relative_paths = (
            Path("Google") / "Chrome" / "Application" / executable_name,
        )
        display_name = "Google Chrome"
    elif browser == "edge":
        executable_name = "msedge.exe"
        shutil_names = ("msedge", "msedge.exe")
        relative_paths = (
            Path("Microsoft") / "Edge" / "Application" / executable_name,
        )
        display_name = "Microsoft Edge"
    else:
        raise RuntimeError(f"Navegador no soportado: {browser_name}")

    for candidate_name in shutil_names:
        discovered = shutil.which(candidate_name)
        if discovered:
            return discovered

    candidates: list[Path] = []
    for key in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        root = str(os.environ.get(key, "")).strip()
        if not root:
            continue
        for relative_path in relative_paths:
            candidates.append(Path(root) / relative_path)

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)

    raise RuntimeError(f"{display_name} no está instalado o no pudo localizarse.")
