"""Storage contract coverage for private employee documents."""

from app.domains.employee_documents.storage import (
    EmployeeDocumentStorage,
    EmployeeDocumentStorageConfig,
    generated_artifact_key,
    signed_version_key,
)


class FakeS3:
    def __init__(self):
        self.presign_calls = []
        self.put_calls = []
        self.get_calls = []
        self.delete_calls = []

    def generate_presigned_url(self, operation, Params, ExpiresIn):
        self.presign_calls.append(
            {"operation": operation, "Params": Params, "ExpiresIn": ExpiresIn}
        )
        return "https://example.invalid/presigned"

    def put_object(self, **kwargs):
        self.put_calls.append(kwargs)
        return {}

    def get_object(self, **kwargs):
        self.get_calls.append(kwargs)

        class Body:
            def read(self):
                return b"payload"

        return {"Body": Body()}

    def delete_object(self, **kwargs):
        self.delete_calls.append(kwargs)
        return {}


def test_signed_keys_never_use_candidate_documents_prefix():
    key = signed_version_key("emp-1", "doc-1", 2, "ver-2")

    assert key == (
        "employee-documents/employees/emp-1/documents/doc-1/"
        "signed/v0002-ver-2.pdf"
    )
    assert not key.startswith("documents/")


def test_generated_keys_are_unique_and_private():
    key = generated_artifact_key("emp-1", "doc-1", "artifact-1", "docx")

    assert key == (
        "employee-documents/employees/emp-1/documents/doc-1/"
        "generated/artifact-1.docx"
    )
    assert not key.startswith("documents/")


def test_storage_config_has_secure_project_defaults(monkeypatch):
    monkeypatch.setenv("EMPLOYEE_DOCUMENTS_BUCKET", "private-bucket")
    monkeypatch.delenv("EMPLOYEE_DOCUMENTS_PREFIX", raising=False)
    monkeypatch.delenv("EMPLOYEE_DOCUMENT_MAX_UPLOAD_BYTES", raising=False)
    monkeypatch.delenv("EMPLOYEE_DOCUMENT_PRESIGN_TTL_SECONDS", raising=False)

    config = EmployeeDocumentStorageConfig.from_env()

    assert config.bucket == "private-bucket"
    assert config.prefix == "employee-documents"
    assert config.max_upload_bytes == 15 * 1024 * 1024
    assert config.presign_ttl_seconds == 300
    assert config.contract_template_key == (
        "templates/contracts/asiati-employment-contract-v1.docx"
    )
    assert config.contract_template_manifest_key == (
        "templates/contracts/asiati-employment-contract-v1.json"
    )


def test_presign_uses_300_second_default():
    fake_s3 = FakeS3()
    storage = EmployeeDocumentStorage(client=fake_s3, bucket="private-bucket")

    url = storage.presign_get(
        "employee-documents/x.pdf",
        filename="Contrato firmado.pdf",
        content_type="application/pdf",
    )

    assert url == "https://example.invalid/presigned"
    call = fake_s3.presign_calls[0]
    assert call["operation"] == "get_object"
    assert call["ExpiresIn"] == 300
    assert call["Params"]["Bucket"] == "private-bucket"
    assert call["Params"]["Key"] == "employee-documents/x.pdf"
    assert call["Params"]["ResponseContentType"] == "application/pdf"
    assert "attachment" in call["Params"]["ResponseContentDisposition"]


def test_storage_put_get_delete_are_scoped_to_configured_bucket():
    fake_s3 = FakeS3()
    storage = EmployeeDocumentStorage(client=fake_s3, bucket="private-bucket")

    storage.put_bytes("employee-documents/a.pdf", b"abc", "application/pdf")
    assert storage.get_bytes("employee-documents/a.pdf") == b"payload"
    storage.delete_object("employee-documents/a.pdf")

    assert fake_s3.put_calls[0]["Bucket"] == "private-bucket"
    assert fake_s3.put_calls[0]["ContentType"] == "application/pdf"
    assert fake_s3.get_calls[0]["Bucket"] == "private-bucket"
    assert fake_s3.delete_calls[0]["Bucket"] == "private-bucket"
