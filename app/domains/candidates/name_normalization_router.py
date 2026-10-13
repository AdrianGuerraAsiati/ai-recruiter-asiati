"""Administrative preview for candidate-name quality, without write side effects."""
import re
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.deps import get_db, require_permission
from app.models import Candidate

router = APIRouter(prefix="/api/candidates/name-normalization", tags=["candidate-name-normalization"])
_SUSPECT = re.compile(
    r"computrabajo|oferta|vacante|curr[ií]culum|hoja de vida|"
    r"no tengo empleo|carnet de conducir|estoy trabajando|"
    r"capacidad|experiencia|planificar|coordinar|habilidades|operaciones",
    re.IGNORECASE,
)

def _flag(name: str) -> str | None:
    if not name or not name.strip():
        return "empty_name"
    if _SUSPECT.search(name):
        return "suspected_import_artifact"
    if "@" in name or any(char.isdigit() for char in name):
        return "invalid_name_characters"
    if len(name.split()) == 1:
        return "single_word_name"
    return None

@router.get("/preview")
def preview_candidate_name_normalization(
    limit: int = Query(100, ge=1, le=250),
    db: Session = Depends(get_db),
    user: dict = Depends(require_permission("candidates.manage")),
):
    # Scan the complete current directory. This is a dry-run audit, not
    # a guessed name replacement and not an LLM invocation.
    rows = db.query(Candidate.id, Candidate.name).filter(
        Candidate.owner_sub == user["sub"]
    ).order_by(Candidate.id).all()
    flagged = []
    reasons = {}
    for candidate_id, name in rows:
        reason = _flag(name)
        if reason:
            reasons[reason] = reasons.get(reason, 0) + 1
            if len(flagged) < limit:
                flagged.append({
                    "candidate_id": str(candidate_id),
                    "current_name": name or "",
                    "reason": reason,
                    "proposed_name": None,
                    "status": "REQUIRES_REVIEW",
                })
    return {
        "total_scanned": len(rows),
        "suspected_count": sum(reasons.values()),
        "reasons": reasons,
        "items": flagged,
        "shown": len(flagged),
        "has_more": len(flagged) < sum(reasons.values()),
        "auto_changed": 0,
    }
