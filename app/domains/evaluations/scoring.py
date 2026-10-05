"""Deterministic weighted scoring for candidate evaluations.

The LLM may classify job requirements, but the final score is always
calculated here using fixed, auditable rules.
"""

from __future__ import annotations

from typing import Any

from app.domains.evaluations.rules import normalize_requirement


IMPORTANCE_WEIGHTS = {
    "CRITICAL": 5.0,
    "HIGH": 3.0,
    "MEDIUM": 2.0,
    "LOW": 1.0,
}

VALID_CATEGORIES = {
    "EDUCATION",
    "EXPERIENCE",
    "TECHNICAL_SKILL",
    "CERTIFICATION_LICENSE",
    "LANGUAGE",
    "AVAILABILITY",
    "SOFT_SKILL",
    "OTHER",
}

STATUS_FACTORS = {
    "MATCH": 1.0,
    "PARTIAL": 0.5,
    "MISSING": 0.0,
}


def _normalize_importance(value: Any, *, mandatory: bool = False) -> str:
    if mandatory:
        return "CRITICAL"
    importance = str(value or "MEDIUM").upper().strip()
    if importance not in IMPORTANCE_WEIGHTS:
        return "MEDIUM"
    return importance


def _normalize_category(value: Any) -> str:
    category = str(value or "OTHER").upper().strip()
    if category not in VALID_CATEGORIES:
        return "OTHER"
    return category


def normalize_requirement_profiles(raw_requirements: list[Any]) -> list[dict]:
    """Normalize requirement extraction output into an internal scoring profile.

    Backward compatibility:
    - legacy string requirements remain supported and are equally weighted;
    - structured requirements use category/importance/mandatory metadata.
    """
    normalized: list[dict] = []
    index_by_key: dict[str, int] = {}

    for raw in raw_requirements:
        is_structured = isinstance(raw, dict)
        if is_structured:
            raw_name = raw.get("requirement", "")
            mandatory = raw.get("mandatory") is True
            importance = _normalize_importance(
                raw.get("importance"),
                mandatory=mandatory,
            )
            category = _normalize_category(raw.get("category"))
            weight = IMPORTANCE_WEIGHTS[importance]
        else:
            raw_name = raw
            mandatory = False
            importance = "MEDIUM"
            category = "OTHER"
            # Preserve the historical equal-weight behavior for legacy payloads.
            weight = 1.0

        if not isinstance(raw_name, str):
            continue

        name = normalize_requirement(raw_name).strip()
        if not name:
            continue

        item = {
            "requirement": name,
            "category": category,
            "importance": importance,
            "mandatory": mandatory,
            "weight": weight,
            "_expose_scoring_metadata": is_structured,
        }
        key = name.casefold()

        existing_index = index_by_key.get(key)
        if existing_index is None:
            index_by_key[key] = len(normalized)
            normalized.append(item)
            continue

        # Merge duplicates conservatively, keeping the strongest job signal.
        existing = normalized[existing_index]
        if item["weight"] > existing["weight"]:
            existing["weight"] = item["weight"]
            existing["importance"] = item["importance"]
            existing["category"] = item["category"]
        existing["mandatory"] = bool(existing["mandatory"] or item["mandatory"])
        existing["_expose_scoring_metadata"] = bool(
            existing["_expose_scoring_metadata"]
            or item["_expose_scoring_metadata"]
        )
        if existing["mandatory"]:
            existing["importance"] = "CRITICAL"
            existing["weight"] = IMPORTANCE_WEIGHTS["CRITICAL"]

    return normalized


def calculate_weighted_match_score(requirements: list[dict]) -> int:
    """Return a deterministic 0-100 weighted match score."""
    if not requirements:
        return 0

    weighted_points = 0.0
    total_weight = 0.0

    for item in requirements:
        try:
            weight = float(item.get("weight", 1.0))
        except (TypeError, ValueError):
            weight = 1.0
        if weight <= 0:
            weight = 1.0

        status = str(item.get("status", "MISSING")).upper().strip()
        factor = STATUS_FACTORS.get(status, 0.0)

        total_weight += weight
        weighted_points += weight * factor

    if total_weight <= 0:
        return 0

    return round((weighted_points / total_weight) * 100)


def mandatory_gaps(requirements: list[dict]) -> list[str]:
    """Return explicit mandatory requirements with no supporting CV evidence."""
    return [
        str(item.get("requirement"))
        for item in requirements
        if item.get("mandatory") is True
        and item.get("status") == "MISSING"
        and item.get("requirement")
    ]
