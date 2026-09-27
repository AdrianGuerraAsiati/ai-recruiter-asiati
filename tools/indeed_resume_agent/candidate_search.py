"""Shared candidate-search normalization for Indeed browser drivers."""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import quote_plus


INDEED_CANDIDATES_HOME = "https://employers.indeed.com/candidates"


def normalize_lookup_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def candidate_search_queries(candidate_name: str) -> list[str]:
    original = " ".join(str(candidate_name or "").split()).strip()
    if not original:
        return []

    normalized = normalize_lookup_text(original)
    queries = [original]
    if normalized and normalized.casefold() != original.casefold():
        queries.append(normalized)

    tokens = normalized.split()
    if len(tokens) >= 3:
        short = f"{tokens[0]} {tokens[-1]}"
        if short not in queries:
            queries.append(short)

    unique: list[str] = []
    seen: set[str] = set()
    for query in queries:
        key = query.casefold()
        if key and key not in seen:
            seen.add(key)
            unique.append(query)
    return unique


def candidate_search_url(query: str) -> str:
    return (
        f"{INDEED_CANDIDATES_HOME}"
        f"?statusName=All&tab=manage&q={quote_plus(str(query or '').strip())}"
    )
