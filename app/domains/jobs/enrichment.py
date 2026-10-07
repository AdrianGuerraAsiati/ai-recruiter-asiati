"""AI-assisted vacancy draft enrichment with tenant company context."""

from __future__ import annotations

import json
from typing import Callable

from langchain_core.prompts import ChatPromptTemplate
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.domains.jobs.company_context import (
    ensure_asiati_context_v1,
    get_active_company_context,
    validated_context_payload,
)
from app.domains.jobs.schemas import JobEnrichmentProposal, JobEnrichmentRequest
from app.infrastructure.bedrock.clients import get_llm
from app.infrastructure.bedrock.parser import invoke_json_prompt


class JobEnrichmentError(RuntimeError):
    """Raised when the model cannot produce a valid enrichment proposal."""


SYSTEM_PROMPT = """
Eres un asistente para personal de Recursos Humanos que mejora borradores de vacantes.
Tu trabajo es proponer un perfil mas preciso y util, nunca decidir por RR. HH.

REGLAS ABSOLUTAS:
- Usa el contexto de empresa solo para mejorar relevancia.
- Los principios de empresa son contexto, no requisitos obligatorios automaticos.
- No inventes herramientas, tecnologias, certificaciones o procesos internos como hechos.
- Si una implicacion del cargo es incierta, incluyela en assumptions_to_validate.
- Separa tecnologias y certificaciones requeridas de las preferidas.
- No uses atributos protegidos ni criterios personales no relacionados con el cargo.
- Redacta EN ESPAÑOL todos los valores de texto generados para la propuesta.
- Usa español profesional y natural para equipos de RR. HH. en Latinoamérica.
- Conserva sin traducir nombres oficiales de tecnologías, productos, certificaciones, siglas y marcas (por ejemplo: AWS, Terraform, Power BI).
- Las claves JSON deben conservar exactamente los nombres definidos en el contrato de salida; solo sus valores de lenguaje natural deben estar en español.
- Devuelve unicamente JSON que cumpla exactamente el contrato de salida.
- Siempre incluye improved_description con una descripcion completa, lista para publicar.
- Siempre devuelve las listas del perfil aunque esten vacias.
{_retry_instruction}
""".strip()


def _build_prompt(request: JobEnrichmentRequest, company_context: dict) -> str:
    output_contract = {
        "improved_description": "string",
        "required_technologies": ["string"],
        "preferred_technologies": ["string"],
        "required_certifications": ["string"],
        "preferred_certifications": ["string"],
        "minimum_years_experience": "number|null",
        "specific_experience": ["string"],
        "responsibilities": ["string"],
        "domain_knowledge": ["string"],
        "education": ["string"],
        "languages": ["string"],
        "technical_competencies": ["string"],
        "assumptions_to_validate": ["string"],
    }
    task_instruction = (
        "MEJORA ITERATIVA: la descripcion recibida ya fue enriquecida previamente. "
        "Usala como base, conserva los hechos utiles, elimina redundancias, mejora claridad y estructura, "
        "fortalece responsabilidades y criterios evaluables sin inventar requisitos. "
        "Devuelve una version claramente mejor que la actual y un perfil completo."
        if request.mode == "improve"
        else (
            "ENRIQUECIMIENTO INICIAL: convierte el borrador en una vacante clara, completa y evaluable, "
            "sin inventar requisitos que no esten sustentados por el cargo o el contexto."
        )
    )
    return "\n\n".join(
        [
            "TASK\n" + task_instruction,
            "COMPANY_CONTEXT\n" + json.dumps(company_context, ensure_ascii=False, sort_keys=True),
            "JOB_DRAFT\n" + json.dumps(request.model_dump(mode="json"), ensure_ascii=False, sort_keys=True),
            (
                "OUTPUT_LANGUAGE\n"
                "es-CO: todos los valores de lenguaje natural deben redactarse en español. "
                "Conserva nombres oficiales de tecnologías, productos, certificaciones, siglas y marcas."
            ),
            "OUTPUT_CONTRACT\n" + json.dumps(output_contract, ensure_ascii=False, sort_keys=True),
        ]
    )


def _default_model_client(prompt: str) -> dict:
    chain = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            ("human", "{prompt}"),
        ]
    ) | get_llm()
    return invoke_json_prompt(
        chain,
        {"prompt": prompt, "_retry_instruction": ""},
        "enriquecer una vacante",
    )


def enrich_job_draft(
    db: Session,
    *,
    owner_sub: str,
    request: JobEnrichmentRequest,
    model_client: Callable[[str], dict] | None = None,
) -> tuple[JobEnrichmentProposal, int | None]:
    """Return an advisory proposal for an unsaved vacancy draft.

    This function may provision tenant configuration (`CompanyContext`) on the
    first call, but it never creates/updates a Job and never evaluates candidates.
    """
    context_row = get_active_company_context(db, owner_sub=owner_sub)
    if context_row is None:
        context_row = ensure_asiati_context_v1(db, owner_sub=owner_sub)

    company_context = validated_context_payload(context_row).model_dump()
    prompt = _build_prompt(request, company_context)
    invoke = model_client or _default_model_client

    try:
        raw = invoke(prompt)
        try:
            proposal = JobEnrichmentProposal.model_validate(raw)
        except (ValidationError, ValueError, TypeError, KeyError):
            repair_prompt = (
                prompt
                + "\n\nVALIDATION_RETRY\n"
                + "La respuesta anterior no cumplio el contrato de salida. "
                + "Devuelve nuevamente SOLO el objeto JSON del OUTPUT_CONTRACT, sin propiedades adicionales. "
                + "improved_description debe ser un string no vacio y todas las colecciones deben ser listas JSON."
            )
            raw = invoke(repair_prompt)
            proposal = JobEnrichmentProposal.model_validate(raw)
    except (ValidationError, ValueError, TypeError, KeyError) as exc:
        raise JobEnrichmentError(
            "El modelo no devolvio una propuesta de vacante valida."
        ) from exc
    except JobEnrichmentError:
        raise
    except Exception as exc:
        raise JobEnrichmentError(
            "No fue posible enriquecer la vacante en este momento."
        ) from exc

    return proposal, int(context_row.version) if context_row is not None else None
