"""Sequential and user-confirmed vacancy applicant handoff to Talent."""
from __future__ import annotations


def sync_visible_candidates(*, browser, api, source_account: str, job_title: str,
                            progress=None, stop_requested=None) -> dict:
    """Import at most the visible page. Identity and duplicates handled by Talent."""
    if not source_account.strip() or not job_title.strip():
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
            document = browser.collect_candidate(candidate)
            answer = api.ingest_source_candidate(
                provider="COMPUTRABAJO",
                source_account=source_account.strip(),
                external_id=str(candidate["external_id"]),
                candidate_name=document["name"],
                job_title=job_title.strip(),
                filename=document["filename"],
                data=document["data"],
                content_type=document["content_type"],
                external_job_id=candidate.get("external_job_id"),
            )
            result["existing" if answer.get("existing") else "created"] += 1
        except Exception as exc:
            result["failed"] += 1
            result["errors"].append({"item": index, "code": type(exc).__name__})
        if progress:
            progress(index, result.copy())
    return result
