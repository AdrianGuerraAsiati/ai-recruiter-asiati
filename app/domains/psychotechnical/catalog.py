"""Versioned objective question bank used by the psychotechnical MVP.

This module intentionally avoids clinical, personality, mental-health, or protected-class
inferences. It measures only job-related reasoning, numerical reasoning, attention to
detail and verbal comprehension. Results are advisory and must not auto-reject candidates.
"""

TEST_KEY = "CORE_REASONING_V1"
TEST_VERSION = 1
TEST_NAME = "Razonamiento y atención"
TEST_DESCRIPTION = (
    "Prueba laboral objetiva de razonamiento lógico, numérico, atención al detalle "
    "y comprensión verbal. No es una evaluación clínica ni de personalidad."
)
DURATION_MINUTES = 20

QUESTIONS = [
    {
        "id": "L1",
        "dimension": "LOGICAL",
        "prompt": "Completa la secuencia: 2, 4, 8, 16, __",
        "options": [
            {"id": "A", "label": "18"},
            {"id": "B", "label": "24"},
            {"id": "C", "label": "32"},
            {"id": "D", "label": "34"},
        ],
        "correct": "C",
    },
    {
        "id": "L2",
        "dimension": "LOGICAL",
        "prompt": "Todos los reportes son documentos. Algunos documentos son confidenciales. ¿Qué se puede concluir?",
        "options": [
            {"id": "A", "label": "Todos los reportes son confidenciales"},
            {"id": "B", "label": "Ningún reporte es confidencial"},
            {"id": "C", "label": "No se puede concluir si algún reporte es confidencial"},
            {"id": "D", "label": "Todos los documentos son reportes"},
        ],
        "correct": "C",
    },
    {
        "id": "L3",
        "dimension": "LOGICAL",
        "prompt": "Completa el patrón: A, C, F, J, O, __",
        "options": [
            {"id": "A", "label": "T"},
            {"id": "B", "label": "U"},
            {"id": "C", "label": "V"},
            {"id": "D", "label": "W"},
        ],
        "correct": "B",
    },
    {
        "id": "N1",
        "dimension": "NUMERICAL",
        "prompt": "¿Cuánto es el 25% de 240?",
        "options": [
            {"id": "A", "label": "40"},
            {"id": "B", "label": "50"},
            {"id": "C", "label": "60"},
            {"id": "D", "label": "80"},
        ],
        "correct": "C",
    },
    {
        "id": "N2",
        "dimension": "NUMERICAL",
        "prompt": "8 personas procesan 120 registros en 3 horas. Al mismo ritmo, ¿cuántos registros procesan 12 personas en 2 horas?",
        "options": [
            {"id": "A", "label": "80"},
            {"id": "B", "label": "100"},
            {"id": "C", "label": "120"},
            {"id": "D", "label": "180"},
        ],
        "correct": "C",
    },
    {
        "id": "N3",
        "dimension": "NUMERICAL",
        "prompt": "Un presupuesto de $4.800.000 se reduce en 12,5%. ¿Cuál es el nuevo valor?",
        "options": [
            {"id": "A", "label": "$4.000.000"},
            {"id": "B", "label": "$4.200.000"},
            {"id": "C", "label": "$4.320.000"},
            {"id": "D", "label": "$4.400.000"},
        ],
        "correct": "B",
    },
    {
        "id": "A1",
        "dimension": "ATTENTION",
        "prompt": "¿Cuál código coincide exactamente con: AX7-19B-Q4?",
        "options": [
            {"id": "A", "label": "AX7-19B-Q4"},
            {"id": "B", "label": "AX7-19B-04"},
            {"id": "C", "label": "AX7-I9B-Q4"},
            {"id": "D", "label": "AX7-19B-QA"},
        ],
        "correct": "A",
    },
    {
        "id": "A2",
        "dimension": "ATTENTION",
        "prompt": "En la cadena A7B3 · A7B8 · A7B3 · A7B3, ¿cuántas veces aparece exactamente A7B3?",
        "options": [
            {"id": "A", "label": "1"},
            {"id": "B", "label": "2"},
            {"id": "C", "label": "3"},
            {"id": "D", "label": "4"},
        ],
        "correct": "C",
    },
    {
        "id": "A3",
        "dimension": "ATTENTION",
        "prompt": "¿Cuál par contiene una diferencia?",
        "options": [
            {"id": "A", "label": "TR-4059 / TR-4059"},
            {"id": "B", "label": "LM-8821 / LM-8821"},
            {"id": "C", "label": "QX-1706 / QX-1760"},
            {"id": "D", "label": "AB-3314 / AB-3314"},
        ],
        "correct": "C",
    },
    {
        "id": "V1",
        "dimension": "VERBAL",
        "prompt": "Si una instrucción dice: “Envía el informe después de validarlo”, ¿qué debe ocurrir primero?",
        "options": [
            {"id": "A", "label": "Enviar el informe"},
            {"id": "B", "label": "Validar el informe"},
            {"id": "C", "label": "Archivar el informe"},
            {"id": "D", "label": "Eliminar el informe"},
        ],
        "correct": "B",
    },
    {
        "id": "V2",
        "dimension": "VERBAL",
        "prompt": "¿Cuál palabra es más cercana en significado a “conciso”?",
        "options": [
            {"id": "A", "label": "Breve"},
            {"id": "B", "label": "Confuso"},
            {"id": "C", "label": "Extenso"},
            {"id": "D", "label": "Indirecto"},
        ],
        "correct": "A",
    },
    {
        "id": "V3",
        "dimension": "VERBAL",
        "prompt": "“El equipo entregó el proyecto antes de la fecha acordada y sin incidencias críticas”. ¿Cuál afirmación está respaldada por el texto?",
        "options": [
            {"id": "A", "label": "El proyecto tuvo sobrecostos"},
            {"id": "B", "label": "La entrega fue posterior al plazo"},
            {"id": "C", "label": "La entrega fue anticipada y sin fallas críticas reportadas"},
            {"id": "D", "label": "El cliente rechazó el proyecto"},
        ],
        "correct": "C",
    },
]

DIMENSION_LABELS = {
    "LOGICAL": "Razonamiento lógico",
    "NUMERICAL": "Razonamiento numérico",
    "ATTENTION": "Atención al detalle",
    "VERBAL": "Comprensión verbal",
}


def public_questions() -> list[dict]:
    return [
        {
            "id": question["id"],
            "dimension": question["dimension"],
            "prompt": question["prompt"],
            "options": question["options"],
        }
        for question in QUESTIONS
    ]
