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


# Bounded, admin-initiated Bedrock proposal generation.
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from uuid import UUID

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException
from pydantic import BaseModel, Field

_MODEL = "us.amazon.nova-pro-v1:0"
_NAME = re.compile(r"^[^\W\d_]+(?:[ '-][^\W\d_]+){1,6}$", re.UNICODE)
_INSTRUCTIONS = (
    "Analyze this CV image and identify ONLY the applicant's full personal "
    "name explicitly visible on the image. Never infer from emails, recruiter "
    "names, reference contacts, or job vacancy titles. Return ONLY JSON with "
    "full_name and exact_visible_evidence keys; null if not visible."
)


class SuggestRequest(BaseModel):
    candidate_ids: list[str] = Field(min_length=1, max_length=5)


class NameApproval(BaseModel):
    candidate_id: str
    expected_current_name: str
    proposed_name: str


class ApplyRequest(BaseModel):
    approvals: list[NameApproval] = Field(min_length=1, max_length=100)


class RevertRequest(BaseModel):
    candidate_id: str
    change_id: str


def _valid_name(name, evidence):
    return bool(
        5 <= len(name) <= 90
        and _NAME.fullmatch(name)
        and not _SUSPECT.search(name)
        and name.casefold() in evidence.casefold()
    )


def _cv_image(cid):
    import pymupdf
    session = boto3.Session(
        profile_name=os.getenv("BEDROCK_AWS_PROFILE") or None,
        region_name="us-east-2",
    )
    bucket = os.getenv("S3_BUCKET")
    if not bucket:
        raise RuntimeError("S3_BUCKET_NOT_CONFIGURED")
    raw = session.client("s3").get_object(
        Bucket=bucket, Key=f"documents/cv-{cid}.pdf"
    )["Body"].read(15 * 1024 * 1024 + 1)
    if len(raw) > 15 * 1024 * 1024:
        raise RuntimeError("CV_TOO_LARGE")
    with pymupdf.open(stream=raw, filetype="pdf") as doc:
        if not doc.page_count:
            raise RuntimeError("EMPTY_CV")
        page = doc[0]
        ratio = min(1.8, 1500 / max(page.rect.width, page.rect.height, 1))
        png = page.get_pixmap(
            matrix=pymupdf.Matrix(ratio, ratio), alpha=False
        ).tobytes("png")
    return session, hashlib.sha256(raw).hexdigest(), png


def _ask_bedrock(session, png):
    response = session.client("bedrock-runtime").converse(
        modelId=_MODEL,
        system=[{"text": _INSTRUCTIONS}],
        messages=[{"role": "user", "content": [
            {"text": "Find the applicant's visible name; reply with JSON only."},
            {"image": {"format": "png", "source": {"bytes": png}}},
        ]}],
        inferenceConfig={"maxTokens":240, "temperature":0},
    )
    raw = "".join(b.get("text", "") for b in response["output"]["message"]["content"]).strip()
    raw = raw.removeprefix(chr(96) * 3 + "json").removeprefix(chr(96) * 3).removesuffix(chr(96) * 3).strip()
    try:
        item = json.loads(raw)
    except (ValueError, TypeError):
        return "", "", "UNRESOLVED"
    if not isinstance(item, dict):
        return "", "", "UNRESOLVED"
    name = " ".join(str(item.get("full_name") or "").split())
    evidence = " ".join(str(item.get("exact_visible_evidence") or "").split())
    if not _valid_name(name, evidence):
        return "", "", "UNRESOLVED"
    return name, evidence[:200], "REVIEW_REQUIRED"


@router.post("/suggest")
def suggest_candidate_names(
    body: SuggestRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(require_permission("candidates.manage")),
):
    if len(body.candidate_ids) != len(set(body.candidate_ids)):
        raise HTTPException(status_code=400, detail="Identificadores duplicados.")
    results = []
    for raw_id in body.candidate_ids:
        try:
            cid = str(UUID(raw_id))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Identificador inválido.") from exc
        candidate = db.query(Candidate).filter(
            Candidate.id == cid, Candidate.owner_sub == user["sub"]
        ).one_or_none()
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidato no encontrado.")
        if not _flag(candidate.name):
            results.append({"candidate_id": cid, "status": "ALREADY_VALID"})
            continue
        try:
            session, digest, image = _cv_image(cid)
            metadata = dict(candidate.metadata_ or {})
            cache = metadata.get("name_normalization") or {}
            cached = cache.get("document_sha256") == digest and cache.get("model") == _MODEL
            if cached:
                name = cache.get("suggested_name") or ""
                evidence = cache.get("evidence") or ""
                status = cache.get("status") or "UNRESOLVED"
            else:
                name, evidence, status = _ask_bedrock(session, image)
                metadata["name_normalization"] = {
                    "document_sha256": digest,
                    "model": _MODEL,
                    "suggested_name": name,
                    "evidence": evidence,
                    "status": status,
                    "evaluated_at": datetime.now(timezone.utc).isoformat(),
                }
                candidate.metadata_ = metadata
                db.commit()
            results.append({
                "candidate_id": cid, "current_name": candidate.name,
                "suggested_name": name, "evidence": evidence,
                "status": status, "cached": cached,
            })
        except (ClientError, BotoCoreError, RuntimeError, ValueError, OSError) as exc:
            db.rollback()
            results.append({"candidate_id": cid, "status": "PROCESSING_ERROR",
                            "error_type": type(exc).__name__})
    return {"items": results}


@router.post("/apply")
def apply_normalized_names(
    body: ApplyRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(require_permission("candidates.manage")),
):
    try:
        ids = [str(UUID(item.candidate_id)) for item in body.approvals]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Identificador inválido.") from exc
    if len(ids) != len(set(ids)):
        raise HTTPException(status_code=400, detail="Identificadores duplicados.")
    batch = str(uuid.uuid4())
    try:
        for approval, cid in zip(body.approvals, ids):
            candidate = db.query(Candidate).filter(
                Candidate.id == cid, Candidate.owner_sub == user["sub"]
            ).with_for_update().one_or_none()
            if candidate is None or candidate.name != approval.expected_current_name:
                raise HTTPException(status_code=409, detail="El candidato ha cambiado.")
            metadata = dict(candidate.metadata_ or {})
            cached = metadata.get("name_normalization") or {}
            name = " ".join(approval.proposed_name.split())
            if (cached.get("status") != "REVIEW_REQUIRED"
                    or cached.get("suggested_name") != name
                    or not _valid_name(name, cached.get("evidence") or "")):
                raise HTTPException(status_code=409, detail="Propuesta no verificada.")
            history = list(metadata.get("name_normalization_history") or [])
            history.append({
                "change_id": str(uuid.uuid4()), "batch_id": batch,
                "previous_name": candidate.name, "new_name": name,
                "approved_by": user["sub"],
                "approved_at": datetime.now(timezone.utc).isoformat(),
                "document_sha256": cached.get("document_sha256"),
            })
            metadata["name_normalization_history"] = history[-30:]
            candidate.metadata_ = metadata
            candidate.name = name
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"applied": len(ids), "batch_id": batch}


@router.post("/revert")
def revert_normalized_name(
    body: RevertRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(require_permission("candidates.manage")),
):
    try:
        cid = str(UUID(body.candidate_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Identificador inválido.") from exc
    candidate = db.query(Candidate).filter(
        Candidate.id == cid, Candidate.owner_sub == user["sub"]
    ).with_for_update().one_or_none()
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidato no encontrado.")
    metadata = dict(candidate.metadata_ or {})
    history = list(metadata.get("name_normalization_history") or [])
    if not history or history[-1].get("change_id") != body.change_id:
        raise HTTPException(status_code=409, detail="Solo se puede revertir el último cambio.")
    last = history[-1]
    if candidate.name != last["new_name"]:
        raise HTTPException(status_code=409, detail="El nombre fue modificado posteriormente.")
    candidate.name = last["previous_name"]
    metadata["name_normalization_history"] = history[:-1]
    metadata["name_normalization_last_reverted"] = {
        **last, "reverted_by": user["sub"],
        "reverted_at": datetime.now(timezone.utc).isoformat(),
    }
    candidate.metadata_ = metadata
    db.commit()
    return {"reverted": True, "candidate_id": cid}


class RevertBatchRequest(BaseModel):
    batch_id: str


@router.post("/revert-batch")
def revert_name_normalization_batch(
    body: RevertBatchRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(require_permission("candidates.manage")),
):
    try:
        batch = str(UUID(body.batch_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Lote inválido.") from exc
    try:
        candidates = db.query(Candidate).filter(
            Candidate.owner_sub == user["sub"]
        ).order_by(Candidate.id).with_for_update().all()
        changes = []
        for candidate in candidates:
            metadata = dict(candidate.metadata_ or {})
            history = list(metadata.get("name_normalization_history") or [])
            if history and history[-1].get("batch_id") == batch:
                last = history[-1]
                if candidate.name != last.get("new_name"):
                    raise HTTPException(
                        status_code=409, detail="Un candidato cambió desde la normalización."
                    )
                changes.append((candidate, metadata, history, last))
        if not changes:
            raise HTTPException(status_code=404, detail="Lote no encontrado o ya revertido.")
        for candidate, metadata, history, last in changes:
            candidate.name = last["previous_name"]
            metadata["name_normalization_history"] = history[:-1]
            metadata["name_normalization_last_reverted"] = {
                **last, "reverted_by": user["sub"],
                "reverted_at": datetime.now(timezone.utc).isoformat(),
            }
            candidate.metadata_ = metadata
        db.commit()
        return {"reverted": len(changes), "batch_id": batch}
    except Exception:
        db.rollback()
        raise


@router.get("/history")
def list_name_normalization_history(
    db: Session = Depends(get_db),
    user: dict = Depends(require_permission("candidates.manage")),
):
    candidates = db.query(Candidate.metadata_).filter(
        Candidate.owner_sub == user["sub"]
    ).all()
    batches = {}
    for (metadata,) in candidates:
        for entry in (metadata or {}).get("name_normalization_history") or []:
            key = entry.get("batch_id")
            if not key:
                continue
            batch = batches.setdefault(key, {
                "batch_id": key, "count": 0,
                "approved_at": entry.get("approved_at"),
            })
            batch["count"] += 1
            if entry.get("approved_at") and entry["approved_at"] > (batch["approved_at"] or ""):
                batch["approved_at"] = entry["approved_at"]
    items = sorted(
        batches.values(), key=lambda item: item.get("approved_at") or "", reverse=True
    )
    return {"items": items[:30]}
