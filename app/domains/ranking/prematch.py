"""Conservative, LLM-free candidate-to-vacancy pre-matching.

This module never creates formal applications or modifies evaluation scores.
Unknown candidate facts remain unknown: absent CV-derived evidence must not
be interpreted as a negative hiring recommendation.
"""
from __future__ import annotations

import re
import unicodedata

from app.domains.jobs.profile import normalize_evaluation_profile

_PRE_RANK_VERSION = "rules-v1"
_EVIDENCE_KEYS = ("cv_profile", "extracted_profile", "resume_profile")


def _normalize(value):
    value = unicodedata.normalize("NFKD", str(value or "").casefold())
    return " ".join("".join(ch for ch in value if not unicodedata.combining(ch)).split())


def _tokens(value):
    return set(re.findall(r"[a-z0-9+#.]{2,}", _normalize(value)))


def _candidate_evidence(candidate):
    metadata = getattr(candidate, "metadata_", None) or {}
    for key in _EVIDENCE_KEYS:
        profile = metadata.get(key)
        if isinstance(profile, dict) and profile:
            return profile
    return {}


def _terms(profile, key):
    value = profile.get(key) or []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return []
    return [str(term).strip() for term in value if str(term).strip()]


def _matches(requirement, evidence):
    required = _tokens(requirement)
    if not required:
        return False
    # Conservative exact phrase or token match; no fabricated semantic equivalence.
    return any(required <= _tokens(item) for item in evidence)


def compare_candidate_job(candidate, job, *, threshold=40):
    """Return an auditable suggestion, not an AI evaluation or application."""
    if not 0 <= threshold <= 100:
        raise ValueError("threshold must be between 0 and 100")
    if bool(getattr(candidate, "is_banned", False)):
        return {"status": "INELIGIBLE", "reason": "CANDIDATE_RESTRICTED"}
    if str(getattr(job, "status", "") or "").upper() != "ACTIVE":
        return {"status": "INELIGIBLE", "reason": "JOB_INACTIVE"}
    mode = str(getattr(job, "work_mode", "") or "ONSITE").upper()
    country = _normalize(getattr(job, "country_code", None))
    candidate_country = _normalize(getattr(candidate, "country_code", None))
    if mode != "REMOTE" and country and candidate_country and candidate_country != country:
        return {"status": "INELIGIBLE", "reason": "COUNTRY_MISMATCH"}
    if mode != "REMOTE" and country and not candidate_country:
        return {"status": "NEEDS_REVIEW", "reason": "COUNTRY_UNKNOWN"}

    evidence = _candidate_evidence(candidate)
    if not evidence:
        return {"status": "NEEDS_REVIEW", "reason": "CV_PROFILE_MISSING"}

    profile = normalize_evaluation_profile(getattr(job, "evaluation_profile", None))
    fields = ("required_technologies", "required_certifications", "specific_experience",
              "domain_knowledge", "education", "languages", "technical_competencies")
    required = [(field, term) for field in fields for term in profile[field]]
    if not required:
        return {"status": "NEEDS_REVIEW", "reason": "JOB_CRITERIA_MISSING"}

    # Only explicit CV-derived facts count as evidence.
    evidence_values = [
        str(entry) for key in ("skills", "technologies", "certifications", "experience",
                               "education", "languages", "competencies", "domains")
        for entry in _terms(evidence, key)
    ]
    if not evidence_values:
        return {"status": "NEEDS_REVIEW", "reason": "PROFILE_EVIDENCE_MISSING"}

    matched = [{"field": field, "requirement": term} for field, term in required if _matches(term, evidence_values)]
    score = round(100 * len(matched) / len(required), 1)
    return {"status": "SUGGESTED" if score >= threshold else "BELOW_THRESHOLD",
            "score": score, "threshold": threshold, "matched": matched,
            "required_count": len(required), "version": _PRE_RANK_VERSION}
