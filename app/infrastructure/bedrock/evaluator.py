"""Candidate evaluation using Bedrock LLM.

Contains the canonical evaluation pipeline using Bedrock LLM.
"""

import json
import logging
import re
import unicodedata

from langchain_core.prompts import ChatPromptTemplate

from app.infrastructure.bedrock.clients import get_llm
from app.infrastructure.bedrock.parser import invoke_json_prompt
from app.infrastructure.bedrock.prompts import (
    CANDIDATE_EVALUATION_PROMPT,
    REQUIREMENT_EXTRACTION_PROMPT,
)
from app.infrastructure.bedrock.retriever import retrieve_candidate
from app.domains.evaluations.rules import (
    MIN_SUMMARY_LENGTH,
    normalize_requirement,
    recommendation_for_score,
)
from app.domains.evaluations.scoring import (
    calculate_weighted_match_score,
    cap_score_for_mandatory_gaps,
    mandatory_gaps,
    normalize_requirement_profiles,
)

logger = logging.getLogger(__name__)


FAILED_EVALUATION_SUMMARY_NO_RESULTS = (
    "No fue posible evaluar al candidato porque "
    "no se encontró información relevante en el Knowledge Base."
)

FAILED_EVALUATION_SUMMARY_NO_REQUIREMENTS = (
    "No se pudieron identificar requisitos explícitos en la descripción de la vacante. "
    "Sin una lista clara de requisitos técnicos o profesionales, no es posible realizar "
    "una evaluación objetiva del perfil del candidato frente a las necesidades del puesto."
)

EVALUATION_FAILED_SUMMARY = (
    "No fue posible completar la evaluación. Intenta nuevamente."
)


def _evidence_key(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(
        character
        for character in text
        if not unicodedata.combining(character)
    )
    text = text.casefold()
    return re.sub(r"\s+", " ", text).strip()


def _evidence_is_grounded(evidence: str, context: str) -> bool:
    """Require positive evidence to be a literal normalized CV fragment."""
    evidence_key = _evidence_key(evidence)
    if len(evidence_key) < 8:
        return False
    return evidence_key in _evidence_key(context)


def evaluate_candidate(
    candidate_id: str,
    job_description: str,
    results: list,
) -> dict:
    """Evaluate a candidate against a job description using LLM.

    Args:
        candidate_id: Canonical candidate UUID
        job_description: Job description text
        results: Retrieval results from Knowledge Base

    Returns:
        dict with: match_score, recommendation, requirements,
        strengths, gaps, summary, status, error_message (if FAILED)
    """
    # No results -> candidate context not found in KB
    if not results:
        return {
            "match_score": 0,
            "recommendation": "EVALUATION_FAILED",
            "requirements": [],
            "strengths": [],
            "gaps": [],
            "summary": FAILED_EVALUATION_SUMMARY_NO_RESULTS,
            "status": "FAILED",
            "error_message": "CANDIDATE_CONTEXT_NOT_FOUND",
        }

    # Build CV context from retrieval results
    context_parts = []
    for result in results:
        text = result.get("content", {}).get("text", "")
        if text:
            context_parts.append(text)
    context = "\n\n---\n\n".join(context_parts)

    # STEP 1: Extract requirements from job description
    extraction_chain = REQUIREMENT_EXTRACTION_PROMPT | get_llm()
    extraction = invoke_json_prompt(
        extraction_chain,
        {"job_description": job_description, "_retry_instruction": ""},
        "extraer requisitos",
    )

    raw_requirements = extraction.get("requirements", [])
    if not isinstance(raw_requirements, list):
        raw_requirements = []

    requirement_profiles = normalize_requirement_profiles(raw_requirements)
    uses_weighted_scoring = any(
        profile.get("_expose_scoring_metadata") is True
        for profile in requirement_profiles
    )

    if not requirement_profiles:
        return {
            "match_score": 0,
            "recommendation": "EVALUATION_FAILED",
            "requirements": [],
            "strengths": [],
            "gaps": [],
            "summary": FAILED_EVALUATION_SUMMARY_NO_REQUIREMENTS,
            "status": "FAILED",
            "error_message": "JOB_REQUIREMENTS_NOT_FOUND",
        }

    # STEP 2: Prepare requirements text
    requirements_text = "\n".join(
        f"- {profile['requirement']}" for profile in requirement_profiles
    )

    # STEP 3: Evaluate requirements against CV
    evaluation_chain = CANDIDATE_EVALUATION_PROMPT | get_llm()
    evaluation = invoke_json_prompt(
        evaluation_chain,
        {"requirements": requirements_text, "context": context, "_retry_instruction": ""},
        "evaluar requisitos contra CV",
    )

    # Normalize evaluation results
    raw_requirements = evaluation.get("requirements", [])
    valid_statuses = {"MATCH", "PARTIAL", "MISSING"}
    evaluated = {}

    for item in raw_requirements:
        if not isinstance(item, dict):
            continue
        requirement = str(item.get("requirement", "")).strip()
        if not requirement:
            continue
        normalized_requirement = normalize_requirement(requirement).strip()
        status = str(item.get("status", "MISSING")).upper().strip()
        if status not in valid_statuses:
            status = "MISSING"
        evidence = item.get("evidence")
        if status == "MISSING":
            evidence = None
        else:
            evidence = str(evidence or "").strip()
            if not evidence or not _evidence_is_grounded(evidence, context):
                # Positive evidence is only creditable when the cited fragment
                # can be found in the retrieved CV context itself.
                status = "MISSING"
                evidence = None
            else:
                words = evidence.split()
                if len(words) > 30:
                    evidence = " ".join(words[:30]) + "..."
        key = normalized_requirement.lower().strip()
        evaluated[key] = {
            "requirement": normalized_requirement,
            "status": status,
            "evidence": evidence,
        }

    # Guarantee all requirements are present and attach the job scoring profile.
    final_requirements = []
    for profile in requirement_profiles:
        normalized_requirement = profile["requirement"]
        key = normalized_requirement.lower().strip()
        existing = evaluated.get(key)

        item = {
            "requirement": normalized_requirement,
            "status": (
                existing.get("status", "MISSING")
                if existing
                else "MISSING"
            ),
            "evidence": existing.get("evidence") if existing else None,
        }

        if profile.get("_expose_scoring_metadata") is True:
            item.update(
                {
                    "category": profile["category"],
                    "importance": profile["importance"],
                    "mandatory": profile["mandatory"],
                    "weight": profile["weight"],
                }
            )

        final_requirements.append(item)

    # Calculate deterministic weighted score.
    total = len(final_requirements)
    match_score = calculate_weighted_match_score(final_requirements)
    missing_mandatory = mandatory_gaps(final_requirements)
    match_score = cap_score_for_mandatory_gaps(
        match_score,
        final_requirements,
    )

    # Recommendation
    recommendation = recommendation_for_score(match_score)

    # Strengths
    strengths = [
        r.get("requirement") for r in final_requirements if r.get("status") == "MATCH"
    ]

    # Gaps
    gaps = [
        r.get("requirement")
        for r in final_requirements
        if r.get("status") in {"PARTIAL", "MISSING"}
    ]

    # Summary
    match_count = sum(1 for r in final_requirements if r["status"] == "MATCH")
    partial_count = sum(1 for r in final_requirements if r["status"] == "PARTIAL")
    missing_count = sum(1 for r in final_requirements if r["status"] == "MISSING")

    # Build a substantial summary (minimum 100 characters)
    parts = []
    parts.append(
        f"El candidato cumple completamente {match_count} de {total} requisitos evaluados"
    )
    if partial_count > 0:
        parts.append(
            f", cumple parcialmente {partial_count} requisito{'s' if partial_count > 1 else ''}"
        )
    if missing_count > 0:
        parts.append(
            f" y no presenta evidencia suficiente para {missing_count} requisito{'s' if missing_count > 1 else ''}"
        )
    parts.append(".")

    if strengths:
        parts.append(
            f" Sus fortalezas principales incluyen: {', '.join(strengths[:3])}."
        )
    if gaps:
        parts.append(
            f" Las áreas de mejora identificadas son: {', '.join(gaps[:3])}."
        )
    if missing_mandatory:
        parts.append(
            " Requiere revisión humana por requisitos obligatorios sin evidencia: "
            f"{', '.join(missing_mandatory[:3])}."
        )

    summary = "".join(parts)

    # Ensure summary is at least 100 characters
    if len(summary.strip()) < MIN_SUMMARY_LENGTH:
        summary = (
            f"El candidato ha sido evaluado contra {total} requisitos del puesto. "
            f"Se identificaron {match_count} requisitos cumplidos, "
            f"{partial_count} requisitos parcialmente cubiertos "
            f"y {missing_count} requisitos sin evidencia suficiente en el CV. "
            f"Este resultado proporciona una visión general del ajuste del perfil "
            f"del candidato a las necesidades específicas de la vacante."
        )

    result = {
        "match_score": match_score,
        "recommendation": recommendation,
        "requirements": final_requirements,
        "strengths": strengths,
        "gaps": gaps,
        "summary": summary,
    }

    if uses_weighted_scoring:
        result.update(
            {
                "scoring_version": "weighted_requirements_v2",
                "mandatory_gaps": missing_mandatory,
            }
        )

    return result
