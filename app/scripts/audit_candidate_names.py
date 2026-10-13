"""Read-only audit of candidate display names before human-approved repairs.

Usage: python -m app.scripts.audit_candidate_names
Uses DATABASE_URL already configured for the app. Prints candidate ids and reasons
only; never changes candidate rows or exposes email/phone.
"""
from __future__ import annotations

import re

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import get_database_url
from app.models import Candidate

_BAD_GENERIC = re.compile(r"^(?:computrabajo[\\s_-]*(?:cv|profile)?|hoja de vida|curriculum vitae|resume|cv)$", re.I)
_DESCRIPTIVE = re.compile(r"\\b(?:capacidad|experiencia|planificar|coordinar|operaciones|habilidades|funciones|responsable|conocimientos)\\b", re.I)


def flag_candidate_name(name: str) -> str | None:
    normalized = " ".join(str(name or "").split()).strip()
    if not normalized or _BAD_GENERIC.fullmatch(normalized):
        return "GENERIC_OR_EMPTY_NAME"
    if _DESCRIPTIVE.search(normalized):
        return "POSSIBLE_PROFILE_DESCRIPTION"
    if len(normalized.split()) > 5 or len(normalized) > 90:
        return "IMPLAUSIBLE_NAME_LENGTH"
    return None


def main() -> None:
    url = get_database_url()
    if not url:
        raise SystemExit("DATABASE_URL is required")
    engine = create_engine(url)
    scanned = flagged = 0
    with Session(engine) as session:
        for candidate_id, name in session.execute(select(Candidate.id, Candidate.name)):
            scanned += 1
            reason = flag_candidate_name(name)
            if reason:
                flagged += 1
                print(f"{candidate_id}\t{reason}")
    print(f"TOTAL_SCANNED={scanned} TOTAL_FLAGGED={flagged} UPDATED=0")


if __name__ == "__main__":
    main()
