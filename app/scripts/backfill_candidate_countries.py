"""Backfill candidate country by reading canonical CVs.

Safe to rerun: candidates already checked from a CV are skipped unless --force.
Manual country choices are never overwritten.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone

from app.db import SessionLocal
from app.domains.candidates import country as candidate_country
from app.infrastructure.imports import documents, storage
from app.infrastructure.imports.documents import DocumentImportError
from app.models import Candidate


def _mark_without_inference(candidate, status: str) -> None:
    metadata = dict(candidate.metadata_ or {})
    current_source = str(metadata.get("country_source") or "").strip().upper()
    if str(candidate.country_code or "").strip() and not current_source:
        metadata["country_source"] = "LEGACY_FALLBACK"
        metadata["country_confidence"] = "LOW"
    metadata["country_checked_at"] = datetime.now(timezone.utc).isoformat()
    metadata["country_review_status"] = status
    candidate.metadata_ = metadata


def run(*, force: bool = False, use_ai: bool = True, limit: int | None = None) -> dict:
    stats = Counter()
    by_country = Counter()
    by_source = Counter()

    with SessionLocal() as db:
        query = db.query(Candidate).order_by(Candidate.created_at.asc(), Candidate.id.asc())
        if limit is not None:
            query = query.limit(max(0, int(limit)))
        candidates = query.all()

        stats["total_candidates"] = len(candidates)
        for candidate in candidates:
            metadata = dict(candidate.metadata_ or {})
            source = str(metadata.get("country_source") or "").strip().upper()
            checked_at = metadata.get("country_checked_at")

            if source == "MANUAL":
                stats["manual_preserved"] += 1
                by_country[str(candidate.country_code or "UNRESOLVED").upper()] += 1
                continue
            if checked_at and not force:
                stats["already_checked"] += 1
                by_country[str(candidate.country_code or "UNRESOLVED").upper()] += 1
                by_source[source or "UNKNOWN"] += 1
                continue

            stats["scanned"] += 1
            try:
                stored = storage.read_existing_canonical_document_with_filename(
                    candidate.id
                )
                if stored is None:
                    _mark_without_inference(candidate, "NO_CANONICAL_CV")
                    db.commit()
                    stats["no_document"] += 1
                    by_country[str(candidate.country_code or "UNRESOLVED").upper()] += 1
                    continue

                data, filename = stored
                parsed = documents.extract_document(data, filename)
                inference = candidate_country.apply_country_inference(
                    db,
                    candidate=candidate,
                    parsed_document=parsed,
                    use_ai=use_ai,
                )
                db.commit()
                db.refresh(candidate)

                if inference.country_code:
                    stats["resolved_from_cv"] += 1
                else:
                    stats["unresolved_from_cv"] += 1
                if inference.source == "CV_AI":
                    stats["resolved_by_ai"] += 1
                elif inference.source.startswith("CV_") and inference.country_code:
                    stats["resolved_deterministically"] += 1

                final_metadata = dict(candidate.metadata_ or {})
                final_source = str(
                    final_metadata.get("country_source") or "UNKNOWN"
                ).upper()
                by_source[final_source] += 1
                by_country[str(candidate.country_code or "UNRESOLVED").upper()] += 1
            except DocumentImportError:
                db.rollback()
                candidate = db.query(Candidate).filter(Candidate.id == candidate.id).one()
                _mark_without_inference(candidate, "CV_PARSE_FAILED")
                db.commit()
                stats["parse_failed"] += 1
                by_country[str(candidate.country_code or "UNRESOLVED").upper()] += 1
            except Exception:
                db.rollback()
                stats["errors"] += 1

    result = dict(stats)
    result["by_country"] = dict(sorted(by_country.items()))
    result["by_source"] = dict(sorted(by_source.items()))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--no-ai", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    result = run(
        force=args.force,
        use_ai=not args.no_ai,
        limit=args.limit,
    )
    print(
        "CANDIDATE_COUNTRY_BACKFILL_JSON="
        + json.dumps(result, ensure_ascii=False, sort_keys=True)
    )


if __name__ == "__main__":
    main()
