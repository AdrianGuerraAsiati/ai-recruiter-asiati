"""Public response presentation for Jobs."""


def job_payload(job, *, candidate_count: int | None = None) -> dict:
    payload = {
        "job_id": job.id,
        "id": job.id,
        "title": job.title,
        "description": job.description,
        "status": getattr(job, "status", None) or "ACTIVE",
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }

    if hasattr(job, "active_description_source"):
        source = getattr(job, "active_description_source", None) or "indeed"
        indeed_description = getattr(job, "indeed_description", None)
        ai_description = getattr(job, "ai_description", None)
        if indeed_description is None and source == "indeed":
            indeed_description = job.description
        if ai_description is None and source == "ai":
            ai_description = job.description
        payload["indeed_description"] = indeed_description
        payload["ai_description"] = ai_description
        payload["active_description_source"] = source

    optional_fields = {
        "country_code": getattr(job, "country_code", None),
        "company_name": getattr(job, "company_name", None),
        "city": getattr(job, "city", None),
        "employment_type": getattr(job, "employment_type", None),
        "response_time_business_days": getattr(job, "response_time_business_days", None),
        "phone_call_count": getattr(job, "phone_call_count", None),
        "onsite_interview_count": getattr(job, "onsite_interview_count", None),
        "offer_wait_days": getattr(job, "offer_wait_days", None),
        "offer_wait_reference": getattr(job, "offer_wait_reference", None),
        "public_slug": getattr(job, "public_slug", None),
    }
    for key, value in optional_fields.items():
        if value is not None:
            payload[key] = value

    published_at = getattr(job, "published_at", None)
    if published_at is not None:
        payload["published_at"] = published_at.isoformat()

    if hasattr(job, "evaluation_version"):
        payload["evaluation_version"] = int(
            getattr(job, "evaluation_version", 1) or 1
        )
        payload["evaluation_profile"] = getattr(job, "evaluation_profile", None) or {}

    if hasattr(job, "_evaluation_changed"):
        payload["evaluation_changed"] = bool(job._evaluation_changed)
        payload["reevaluation_scheduled"] = bool(
            getattr(job, "_reevaluation_scheduled", False)
        )
        payload["reevaluation_candidate_count"] = int(
            getattr(job, "_reevaluation_candidate_count", 0) or 0
        )

    if candidate_count is not None:
        payload["candidate_count"] = candidate_count
    return payload


def delete_job_payload(job_id: str, delete_candidates: bool, deleted_candidates: int) -> dict:
    return {
        "detail": (
            "Vacante y candidatos eliminados."
            if delete_candidates
            else "Vacante eliminada."
        ),
        "job_id": job_id,
        "delete_candidates": delete_candidates,
        "deleted_candidates": deleted_candidates if delete_candidates else 0,
    }
