"""Candidate-only Computrabajo ingestion, with durable local progress.

Employer offers are used strictly as navigation. No offer is created in Talent
and a candidate is never linked to a Talent vacancy during this handoff.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


def _checkpoint_file(browser, source_account: str) -> Path:
    folder = Path(browser.profile_dir).parent / "sync-checkpoints"
    account_hash = hashlib.sha256(source_account.casefold().encode()).hexdigest()[:24]
    return folder / f"computrabajo-{account_hash}.json"


def _read_completed(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("version") != 1 or not isinstance(value.get("completed"), list):
            raise ValueError("COMPUTRABAJO_CHECKPOINT_INVALID")
        return set(x for x in value["completed"] if isinstance(x, str) and len(x) == 64)
    except (OSError, ValueError, TypeError) as exc:
        raise ValueError("COMPUTRABAJO_CHECKPOINT_INVALID") from exc


def _mark_completed(path: Path, completed: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    try:
        temp.write_text(json.dumps({
            "version": 1, "completed": sorted(completed),
        }), encoding="utf-8")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _fingerprint(source_account: str, external_id: str) -> str:
    return hashlib.sha256(
        (source_account.casefold() + "\0" + external_id.casefold()).encode("utf-8")
    ).hexdigest()


class CandidateTransferError(RuntimeError):
    """Safe, non-PII failure description for the agent interface."""

    def __init__(self, stage: str, code: str):
        self.stage = stage
        self.code = code
        super().__init__(f"{stage}:{code}")


def _safe_transfer_code(exc: Exception) -> str:
    # A status code distinguishes API incompatibility from missing PDF.
    status = getattr(exc, "status_code", None)
    if isinstance(status, int) and 400 <= status <= 599:
        return f"HTTP_{status}"
    message = str(exc)
    if message.startswith("COMPUTRABAJO_") and message.isascii() and len(message) < 90:
        return message
    return type(exc).__name__


def _submit_candidate(*, browser, api, source_account: str, candidate: dict) -> dict:
    try:
        document = browser.collect_candidate(candidate)
    except Exception as exc:
        raise CandidateTransferError("descarga", _safe_transfer_code(exc)) from exc
    try:
        # No job title or external job identifier is sent to Talent.
        return api.ingest_source_candidate(
            provider="COMPUTRABAJO",
            source_account=source_account,
            external_id=str(candidate["external_id"]),
            candidate_name=document["name"],
            filename=document["filename"],
            data=document["data"],
            content_type=document["content_type"],
            job_title="",
        )
    except Exception as exc:
        raise CandidateTransferError("talent", _safe_transfer_code(exc)) from exc


def sync_all_candidates(*, browser, api, source_account: str,
                        max_pages: int = 500, checkpoint_path: Path | None = None,
                        progress=None, stop_requested=None,
                        discovery_progress=None) -> dict:
    """Discover accessible candidate pages and sync only previously unseen people."""
    account = source_account.strip()
    if not account:
        raise ValueError("COMPUTRABAJO_CONTEXT_REQUIRED")
    path = Path(checkpoint_path) if checkpoint_path else _checkpoint_file(browser, account)
    completed = _read_completed(path)
    directory = browser.discover_all_candidates(
        max_pages=max_pages, stop_requested=stop_requested,
        discovery_progress=discovery_progress,
    )
    candidates = directory["candidates"]
    result = {
        "total": len(candidates), "created": 0, "existing": 0,
        "skipped": 0, "failed": 0,
        "pages": directory["pages"], "partial": directory["partial"],
        "cancelled": directory["cancelled"], "errors": [],
        "blocked_pages": directory.get("blocked_pages", 0), "error_counts": {},
        "offers_found": directory.get("offers_found", 0),
        "candidate_pages": directory.get("candidate_pages", 0),
        "listing_pages": directory.get("listing_pages", 0),
        "unresolved_pagination": directory.get("unresolved_pagination", 0),
        "reported_received_total": directory.get("reported_received_total", 0),
        "discovered_with_reported_total": directory.get("discovered_with_reported_total", 0),
        "offers_with_missing_candidates": directory.get("offers_with_missing_candidates", 0),
    }
    for index, candidate in enumerate(candidates, 1):
        if stop_requested and stop_requested():
            result["cancelled"] = True
            break
        key = _fingerprint(account, str(candidate["external_id"]))
        if key in completed:
            result["skipped"] += 1
        else:
            try:
                answer = _submit_candidate(
                    browser=browser, api=api, source_account=account,
                    candidate=candidate,
                )
                if not answer.get("queued"):
                    raise RuntimeError("COMPUTRABAJO_CANDIDATE_NOT_QUEUED")
                completed.add(key)
                _mark_completed(path, completed)
                result["existing" if answer.get("existing") else "created"] += 1
            except Exception as exc:
                result["failed"] += 1
                # No candidate identifiers, names, or sensitive provider errors in logs.
                code = (
                    f"{exc.stage}:{exc.code}" if isinstance(exc, CandidateTransferError)
                    else f"local:{type(exc).__name__}"
                )
                result["errors"].append({"item": index, "code": code})
                result["error_counts"][code] = result["error_counts"].get(code, 0) + 1
        if progress:
            progress(index, result.copy())
    return result


def sync_visible_candidates(*, browser, api, source_account: str, job_title: str = "",
                            progress=None, stop_requested=None) -> dict:
    """Backward-compatible one-page operation; never sends or creates a job."""
    if not source_account.strip():
        raise ValueError("COMPUTRABAJO_CONTEXT_REQUIRED")
    candidates = browser.discover_visible_candidates()
    if not candidates:
        raise ValueError("COMPUTRABAJO_NO_CANDIDATES")
    result = dict(total=len(candidates), created=0, existing=0, failed=0,
                  cancelled=False, errors=[])
    for index, candidate in enumerate(candidates, 1):
        if stop_requested and stop_requested():
            result["cancelled"] = True
            break
        try:
            answer = _submit_candidate(
                browser=browser, api=api, source_account=source_account.strip(),
                candidate=candidate,
            )
            result["existing" if answer.get("existing") else "created"] += 1
        except Exception as exc:
            result["failed"] += 1
            result["errors"].append({"item": index, "code": type(exc).__name__})
        if progress:
            progress(index, result.copy())
    return result
