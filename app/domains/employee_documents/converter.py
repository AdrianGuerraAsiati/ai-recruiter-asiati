"""DOCX to reference-PDF conversion through LibreOffice headless."""

from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile

import fitz


class DocumentConversionError(RuntimeError):
    pass


def convert_docx_to_pdf(
    docx_bytes: bytes,
    *,
    timeout_seconds: int = 30,
) -> bytes:
    try:
        with tempfile.TemporaryDirectory(prefix="employee-document-") as directory:
            workdir = Path(directory)
            source = workdir / "source.docx"
            target = workdir / "source.pdf"
            source.write_bytes(docx_bytes)
            try:
                result = subprocess.run(
                    [
                        "libreoffice",
                        "--headless",
                        "--convert-to",
                        "pdf",
                        "--outdir",
                        str(workdir),
                        str(source),
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                    shell=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise DocumentConversionError(
                    "La conversión del documento excedió el tiempo permitido."
                ) from exc
            except OSError as exc:
                raise DocumentConversionError(
                    "El conversor de documentos no está disponible."
                ) from exc

            if result.returncode != 0 or not target.exists():
                raise DocumentConversionError(
                    "No fue posible convertir el DOCX a PDF."
                )
            pdf_bytes = target.read_bytes()
    except DocumentConversionError:
        raise
    except Exception as exc:
        raise DocumentConversionError(
            "No fue posible preparar el PDF de referencia."
        ) from exc

    if not pdf_bytes.startswith(b"%PDF-"):
        raise DocumentConversionError(
            "El conversor no produjo un PDF válido."
        )
    try:
        pdf = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            if pdf.page_count <= 0:
                raise DocumentConversionError(
                    "El PDF de referencia no contiene páginas."
                )
        finally:
            pdf.close()
    except DocumentConversionError:
        raise
    except Exception as exc:
        raise DocumentConversionError(
            "El PDF de referencia no es legible."
        ) from exc
    return pdf_bytes
