"""Conservative identity extraction from a CV (PDF or DOCX).

Only explicit full-name fields or a repeated standalone name adjacent to contact
information are usable. Returns an unresolved result rather than guessing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
_LABEL = re.compile(r"^(?:nombre(?:\s+completo)?|nombres?\s+y\s+apellidos?|apellidos?\s+y\s+nombres?)\s*[:\-]\s*(.+)$", re.I)
_BAD = re.compile(r"\b(?:oferta|vacante|computrabajo|curr[ií]culum|hoja de vida|carnet|veh[ií]culo|disponibilidad|experiencia|perfil|director financiero|no tengo empleo|estoy trabajando|referencias|educaci[oó]n|formaci[oó]n|habilidades)\b", re.I)
_NAME = re.compile(r"^[^\W\d_]+(?:[ '\-][^\W\d_]+){1,5}$", re.UNICODE)


@dataclass(frozen=True)
class NameEvidence:
    name: str | None
    status: str  # VERIFIED_LABEL, REVIEW_CV_CONTEXT, UNRESOLVED, CONFLICT
    evidence: str  # evidence type only; no personal data


def _plausible(value: str) -> bool:
    return (5 <= len(value) <= 80 and bool(_NAME.fullmatch(value))
            and not _BAD.search(value) and not _EMAIL.search(value))


def detect_cv_name(data: bytes, filename: str) -> NameEvidence:
    """Return a name when labeled in the document; never infer from email/file name.

    DOCX and PDF share text parsing via the existing document-import pipeline.
    Exceptions signal an unreadable document and should be handled by caller.
    """
    from app.infrastructure.imports.documents import extract_document

    parsed = extract_document(data, filename)
    lines = [" ".join(s.split()) for s in parsed.text.splitlines()]
    lines = [s for s in lines if s]
    explicit = []
    for line in lines[:100]:
        match = _LABEL.match(line)
        if match and _plausible(match.group(1)):
            explicit.append(match.group(1))
    unique = list(dict.fromkeys(s.casefold() for s in explicit))
    if len(unique) == 1:
        return NameEvidence(explicit[0], "VERIFIED_LABEL", "explicit_name_field")
    if len(unique) > 1:
        return NameEvidence(None, "CONFLICT", "conflicting_name_fields")

    # Standalone text near an email is a review cue, NOT independently verified.
    contact_positions = [i for i, line in enumerate(lines[:80]) if _EMAIL.search(line)]
    candidates = []
    for i in contact_positions:
        for line in lines[max(0, i - 4):i]:
            if _plausible(line):
                candidates.append(line)
    distinct = list(dict.fromkeys(s.casefold() for s in candidates))
    if len(distinct) == 1:
        return NameEvidence(candidates[0], "REVIEW_CV_CONTEXT", "adjacent_to_email")
    return NameEvidence(None, "UNRESOLVED", "insufficient_identity_evidence")
