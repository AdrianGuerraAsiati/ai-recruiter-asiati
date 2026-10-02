"""Template rendering and reference-PDF generation contracts."""

from __future__ import annotations

from io import BytesIO
import json
import subprocess

import fitz
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.domains.employee_documents import generation
from app.domains.employee_documents.converter import (
    DocumentConversionError,
    convert_docx_to_pdf,
)
from app.domains.employee_documents.template import (
    MissingTemplateVariables,
    TemplateManifest,
    TemplateValidationError,
    render_docx,
)
from app.domains.employee_documents.storage import EmployeeDocumentStorageConfig
from app.models import (
    EmployeeDocument,
    EmployeeDocumentArtifact,
    EmployeeDocumentVersion,
    OdooContractSync,
    UserProfile,
)
from app.tests.fixtures.employee_documents.build_test_template import (
    build_template,
    extract_all_text,
)


MANIFEST = {
    "template_version": "1",
    "document_type": "CONTRACT",
    "fields": [
        {
            "name": "employee_full_name",
            "label": "Nombre completo",
            "source": "employee.full_name",
            "required": True,
        },
        {
            "name": "employee.job_title",
            "label": "Cargo",
            "source": "employee.job_title",
            "required": True,
        },
        {
            "name": "contract.monthly_wage",
            "label": "Salario",
            "source": "contract.monthly_wage",
            "required": True,
        },
        {
            "name": "employee_document_number",
            "label": "Documento de identidad",
            "source": "manual",
            "required": True,
        },
    ],
}


class FakeStorage:
    def __init__(self, *, template_bytes=None, manifest=None, fail_on_put_number=None):
        self.config = EmployeeDocumentStorageConfig(bucket="test-documents")
        self.objects = {
            self.config.contract_template_key: template_bytes or build_template(),
            self.config.contract_template_manifest_key: json.dumps(
                manifest or MANIFEST
            ).encode("utf-8"),
        }
        self.put_calls = []
        self.delete_calls = []
        self.fail_on_put_number = fail_on_put_number

    def get_bytes(self, key):
        if key not in self.objects:
            raise KeyError(key)
        return self.objects[key]

    def put_bytes(self, key, body, content_type):
        self.put_calls.append((key, bytes(body), content_type))
        if self.fail_on_put_number == len(self.put_calls):
            raise RuntimeError("simulated storage failure")
        self.objects[key] = bytes(body)

    def delete_object(self, key):
        self.delete_calls.append(key)
        self.objects.pop(key, None)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            UserProfile.__table__,
            OdooContractSync.__table__,
            EmployeeDocument.__table__,
            EmployeeDocumentArtifact.__table__,
            EmployeeDocumentVersion.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    session = Session()
    employee = UserProfile(
        id="employee-gen-1",
        cognito_sub="employee-gen-sub",
        email="ana@asiati.com.co",
        first_name="Ana",
        last_name="Pérez",
        job_title="Desarrolladora",
        department="Tecnología",
        status="ACTIVE",
    )
    session.add(employee)
    session.commit()
    contract_sync = OdooContractSync(
        id="11111111-1111-1111-1111-111111111111",
        employee_id=employee.id,
        idempotency_key=f"contract:{employee.id}",
        payload={
            "schema_version": 1,
            "operation": "UPSERT_CONTRACT",
            "contract": {
                "contract_type": "Indefinido",
                "start_date": "2026-10-05",
                "end_date": None,
                "monthly_wage": "3500000",
            },
        },
        status="PENDING",
    )
    session.add(contract_sync)
    session.commit()
    document = EmployeeDocument(
        id="22222222-2222-2222-2222-222222222222",
        employee_id=employee.id,
        document_type="CONTRACT",
        title="Contrato laboral",
        status="DRAFT",
        contract_sync_id=contract_sync.id,
        created_by_sub="admin-sub",
    )
    session.add(document)
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _valid_pdf_bytes():
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "Contrato de referencia")
    data = pdf.tobytes()
    pdf.close()
    return data


def test_manifest_accepts_only_known_sources():
    manifest = TemplateManifest.from_json_bytes(json.dumps(MANIFEST).encode())

    assert manifest.template_version == "1"
    assert manifest.document_type == "CONTRACT"
    assert manifest.fields[-1].source == "manual"

    invalid = dict(MANIFEST)
    invalid["fields"] = [
        {
            "name": "mystery",
            "label": "Mystery",
            "source": "llm.magic",
            "required": True,
        }
    ]
    with pytest.raises(TemplateValidationError):
        TemplateManifest.from_json_bytes(json.dumps(invalid).encode())


def test_render_docx_replaces_single_run_placeholders_and_preserves_text():
    manifest = TemplateManifest.from_json_bytes(json.dumps(MANIFEST).encode())

    rendered = render_docx(
        build_template(),
        variables={
            "employee_full_name": "Ana Pérez",
            "employee.job_title": "Desarrolladora",
            "contract.monthly_wage": "3500000",
            "employee_document_number": "CC 123456789",
        },
        manifest=manifest,
    )

    text = extract_all_text(rendered)
    assert "{{ employee_full_name }}" not in text
    assert "Ana Pérez" in text
    assert "Salario: 3500000" in text
    assert "ASIATI · Desarrolladora" in text
    assert "Documento CC 123456789" in text


def test_render_docx_rejects_placeholder_split_across_runs():
    manifest = TemplateManifest.from_json_bytes(json.dumps(MANIFEST).encode())

    with pytest.raises(TemplateValidationError):
        render_docx(
            build_template(split_placeholder=True),
            variables={
                "employee_full_name": "Ana Pérez",
                "employee.job_title": "Desarrolladora",
                "contract.monthly_wage": "3500000",
                "employee_document_number": "CC 123",
            },
            manifest=manifest,
        )


def test_convert_docx_runs_libreoffice_headless(monkeypatch, tmp_path):
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        outdir = args[args.index("--outdir") + 1]
        from pathlib import Path

        Path(outdir, "source.pdf").write_bytes(_valid_pdf_bytes())
        return subprocess.CompletedProcess(args, 0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = convert_docx_to_pdf(build_template(), timeout_seconds=30)

    assert result.startswith(b"%PDF-")
    args, kwargs = calls[0]
    assert args[:3] == ["libreoffice", "--headless", "--convert-to"]
    assert "pdf" in args
    assert kwargs["timeout"] == 30
    assert kwargs["shell"] is False


def test_convert_docx_timeout_is_sanitized(monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="libreoffice", timeout=30)

    monkeypatch.setattr(subprocess, "run", timeout)

    with pytest.raises(DocumentConversionError):
        convert_docx_to_pdf(build_template(), timeout_seconds=30)


def test_generation_context_exposes_manual_field_and_blocks_missing_value(db):
    storage = FakeStorage()

    context = generation.resolve_contract_generation_context(
        db,
        employee_id="employee-gen-1",
        document_id="22222222-2222-2222-2222-222222222222",
        storage=storage,
    )

    manual = context["manual_fields"]
    assert manual == [
        {
            "name": "employee_document_number",
            "label": "Documento de identidad",
            "required": True,
            "value": None,
        }
    ]
    assert context["resolved_values"]["employee_full_name"] == "Ana Pérez"
    assert context["resolved_values"]["contract.monthly_wage"] == "3500000"

    with pytest.raises(MissingTemplateVariables) as error:
        generation.generate_contract_artifacts(
            db,
            employee_id="employee-gen-1",
            document_id="22222222-2222-2222-2222-222222222222",
            manual_values={},
            actor_sub="admin-sub",
            storage=storage,
        )
    assert "employee_document_number" in error.value.fields


def test_second_artifact_upload_failure_cleans_first_and_keeps_draft(
    db, monkeypatch
):
    storage = FakeStorage(fail_on_put_number=2)
    monkeypatch.setattr(
        generation,
        "convert_docx_to_pdf",
        lambda *_args, **_kwargs: _valid_pdf_bytes(),
    )

    with pytest.raises(generation.DocumentGenerationError):
        generation.generate_contract_artifacts(
            db,
            employee_id="employee-gen-1",
            document_id="22222222-2222-2222-2222-222222222222",
            manual_values={"employee_document_number": "CC 123456789"},
            actor_sub="admin-sub",
            storage=storage,
        )

    document = (
        db.query(EmployeeDocument)
        .filter(EmployeeDocument.id == "22222222-2222-2222-2222-222222222222")
        .one()
    )
    assert document.status == "DRAFT"
    assert db.query(EmployeeDocumentArtifact).count() == 0
    assert len(storage.put_calls) == 2
    assert storage.delete_calls == [storage.put_calls[0][0]]
