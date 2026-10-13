from unittest.mock import patch

from app.domains.candidates.cv_name_detection import detect_cv_name
from app.infrastructure.imports.documents import ParsedDocument


def check_text(text):
    parsed = ParsedDocument(
        filename="cv.pdf", content_type="application/pdf",
        display_name="computrabajo-profile", email=None, phone=None,
        text=text, header_text=text, sha256="hash",
    )
    with patch("app.infrastructure.imports.documents.extract_document", return_value=parsed):
        return detect_cv_name(b"%PDF-example", "cv.pdf")


def test_explicit_label_recovers_identity():
    result = check_text("Oferta Director financiero - Latam\nNombre completo: Ana María Torres\nCorreo: ana@example.com")
    assert result.name == "Ana María Torres"
    assert result.status == "VERIFIED_LABEL"


def test_job_title_and_email_are_not_names():
    result = check_text("Oferta Director financiero - Latam\nNo tengo empleo\nana@example.com")
    assert result.name is None
    assert result.status == "UNRESOLVED"


def test_conflicting_labels_do_not_produce_name():
    result = check_text("Nombre: Ana María Torres\nNombre: Marta López")
    assert result.name is None
    assert result.status == "CONFLICT"


def test_context_name_requires_human_review():
    result = check_text("Sandra Patricia Ruiz\nsandra@example.com")
    assert result.name == "Sandra Patricia Ruiz"
    assert result.status == "REVIEW_CV_CONTEXT"
