"""Explicit, user-confirmed Computrabajo-to-Talent candidate document handoff."""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path

MAX_BYTES = 15 * 1024 * 1024
REQUIRED = ("external_id", "candidate_name", "job_title", "file")


def prepare_candidate(*, external_id: str, candidate_name: str, job_title: str,
                      file_path: str, source_account: str) -> dict:
    if not all(str(x or "").strip() for x in
               (external_id, candidate_name, job_title, source_account)):
        raise ValueError("Completa identificador, nombre, vacante y cuenta de origen.")
    path = Path(file_path).expanduser().resolve(strict=True)
    if path.suffix.lower() not in (".pdf", ".docx"):
        raise ValueError("Solo se permiten documentos PDF o DOCX.")
    if not path.is_file() or not (0 < path.stat().st_size <= MAX_BYTES):
        raise ValueError("Archivo vacío o superior a 15 MB.")
    data = path.read_bytes()
    if path.suffix.lower() == ".pdf":
        if not data.lstrip().startswith(b"%PDF-"):
            raise ValueError("El PDF no tiene una cabecera válida.")
        mime = "application/pdf"
    else:
        import io
        import zipfile
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                if not {"[Content_Types].xml", "word/document.xml"}.issubset(z.namelist()):
                    raise ValueError("DOCX inválido.")
        except (zipfile.BadZipFile, OSError) as exc:
            raise ValueError("DOCX inválido.") from exc
        mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return dict(external_id=str(external_id).strip(),
                candidate_name=str(candidate_name).strip(),
                job_title=str(job_title).strip(),
                source_account=str(source_account).strip(),
                filename=path.name, data=data, content_type=mime)


def upload_candidate(api, payload: dict) -> dict:
    return api.ingest_source_candidate(
        provider="COMPUTRABAJO", **payload
    )


def load_manifest(csv_path: str) -> list[dict]:
    path = Path(csv_path).expanduser().resolve(strict=True)
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames or not set(REQUIRED).issubset(reader.fieldnames):
            raise ValueError("CSV requiere external_id,candidate_name,job_title,file")
        rows = list(reader)
    if not rows or len(rows) > 100:
        raise ValueError("El lote debe tener de 1 a 100 filas.")
    if len({r["external_id"].strip() for r in rows}) != len(rows):
        raise ValueError("Hay identificadores duplicados en el CSV.")
    for row in rows:
        file_name = Path(row["file"])
        if not file_name.is_absolute():
            row["file"] = str((path.parent / file_name).resolve())
    return rows


def upload_manifest(api, *, csv_path: str, source_account: str) -> dict:
    rows = load_manifest(csv_path)
    result = {"created": 0, "existing": 0, "failed": 0, "errors": []}
    for index, row in enumerate(rows, start=2):
        try:
            payload = prepare_candidate(
                external_id=row["external_id"], candidate_name=row["candidate_name"],
                job_title=row["job_title"], file_path=row["file"],
                source_account=source_account,
            )
            response = upload_candidate(api, payload)
            result["existing" if response.get("existing") else "created"] += 1
        except Exception as exc:
            result["failed"] += 1
            result["errors"].append(f"Fila {index}: {type(exc).__name__}")
    return result
