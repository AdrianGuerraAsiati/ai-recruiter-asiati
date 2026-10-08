"""Canonical document and information requirements for new ASIATI employees."""

from __future__ import annotations


EMPLOYEE_DOCUMENT_REQUIREMENTS = (
    {
        "value": "RESUME",
        "label": "Hoja de vida actualizada",
        "kind": "FILE",
        "description": "Hoja de vida vigente y legible.",
    },
    {
        "value": "IDENTITY",
        "label": "Documento de identidad",
        "kind": "FILE",
        "description": "Copia legible del documento de identidad.",
    },
    {
        "value": "BANK_CERTIFICATE",
        "label": "Certificación bancaria",
        "kind": "FILE",
        "description": "Certificación bancaria vigente para el pago de nómina.",
    },
    {
        "value": "EDUCATION_CERTIFICATES",
        "label": "Certificaciones académicas",
        "kind": "FILE",
        "description": "Diplomas, actas, títulos o certificados académicos aplicables.",
    },
    {
        "value": "EMPLOYMENT_CERTIFICATES",
        "label": "Certificados laborales",
        "kind": "FILE",
        "description": "Certificaciones que soporten la experiencia laboral reportada.",
    },
    {
        "value": "EPS_CERTIFICATE",
        "label": "Certificado de EPS",
        "kind": "FILE",
        "description": "Certificado vigente de afiliación a EPS.",
    },
    {
        "value": "AFP_SEVERANCE_CERTIFICATE",
        "label": "Certificado de AFP y cesantías",
        "kind": "FILE",
        "description": "Certificado de fondo de pensiones y cesantías.",
    },
    {
        "value": "BENEFICIARIES",
        "label": "Documento de beneficiarios",
        "kind": "FILE",
        "description": "Soporte de beneficiarios requerido para la vinculación.",
    },
    {
        "value": "RESIDENCE_ADDRESS",
        "label": "Dirección de residencia",
        "kind": "TEXT",
        "description": "Dirección actual de residencia.",
    },
    {
        "value": "MARITAL_STATUS",
        "label": "Estado civil",
        "kind": "TEXT",
        "description": "Estado civil informado para la vinculación.",
    },
    {
        "value": "EMERGENCY_CONTACT",
        "label": "Contacto de emergencia",
        "kind": "TEXT",
        "description": "Nombre, parentesco y teléfono del contacto de emergencia.",
    },
    {
        "value": "EDUCATION_LEVEL",
        "label": "Nivel de escolaridad",
        "kind": "TEXT",
        "description": "Máximo nivel de escolaridad alcanzado.",
    },
    {
        "value": "BACKGROUND_CHECKS",
        "label": "Antecedentes de Policía, Contraloría y Procuraduría",
        "kind": "FILE",
        "description": "Soportes de antecedentes; se puede cargar un PDF consolidado.",
    },
)

EMPLOYEE_DOCUMENT_REQUIREMENTS_BY_VALUE = {
    item["value"]: item for item in EMPLOYEE_DOCUMENT_REQUIREMENTS
}


def get_requirement(document_type: str) -> dict | None:
    return EMPLOYEE_DOCUMENT_REQUIREMENTS_BY_VALUE.get(
        str(document_type or "").strip().upper()
    )
