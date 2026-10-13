"""Versioned, idempotent pre-match snapshots independent of formal applications."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from app.domains.jobs.profile import normalize_evaluation_profile
from app.domains.ranking.prematch import compare_candidate_job

STORE_KEY = "prematch_v1"


def _hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def candidate_signature(candidate) -> str:
    meta = candidate.metadata_ or {}
    evidence = {}
    for name in ("cv_profile", "extracted_profile", "resume_profile"):
        if isinstance(meta.get(name), dict) and meta[name]:
            evidence = meta[name]
            break
    return _hash({"profile": evidence, "country": candidate.country_code, "banned": candidate.is_banned})


def job_signature(job) -> str:
    return _hash({
        "profile": normalize_evaluation_profile(job.evaluation_profile),
        "country": job.country_code,
        "work_mode": job.work_mode,
        "status": job.status,
        "evaluation_version": job.evaluation_version,
    })


def refresh_candidate_suggestions(db, candidate, jobs, *, threshold: int = 40):
    """Store only suggestions and unknowns; do not create a JobCandidate.

    A content-signature hit avoids repeat CPU work. Inactive vacancies are
    pruned, so stale associations cannot appear in the suggestion list.
    """
    meta = dict(candidate.metadata_ or {})
    previous = meta.get(STORE_KEY) or {}
    prev_items = previous.get("items") or {}
    cand_hash = candidate_signature(candidate)
    active_jobs = [job for job in jobs if str(job.status or "").upper() == "ACTIVE"]
    entries = {}
    reused = 0
    computed = 0
    for job in active_jobs:
        signature = job_signature(job)
        cached = prev_items.get(str(job.id)) if previous.get("candidate_signature") == cand_hash and previous.get("threshold") == threshold else None
        if isinstance(cached, dict) and cached.get("job_signature") == signature:
            result = cached
            reused += 1
        else:
            result = {**compare_candidate_job(candidate, job, threshold=threshold),
                      "job_signature": signature}
            computed += 1
        if result.get("status") in ("SUGGESTED", "NEEDS_REVIEW"):
            entries[str(job.id)] = result
    candidate.metadata_ = {
        **meta,
        STORE_KEY: {
            "candidate_signature": cand_hash,
            "threshold": threshold,
            "version": "rules-v1",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "items": entries,
        },
    }
    db.commit()
    return {"candidate_id": str(candidate.id), "jobs_checked": len(active_jobs),
            "suggested": sum(x["status"] == "SUGGESTED" for x in entries.values()),
            "needs_review": sum(x["status"] == "NEEDS_REVIEW" for x in entries.values()),
            "reused": reused, "computed": computed}
