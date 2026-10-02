"""Private S3 storage for confidential employee documents."""

from __future__ import annotations

from dataclasses import dataclass
import os
from urllib.parse import quote

from app.infrastructure.bedrock.session import get_cached_session


DEFAULT_PREFIX = "employee-documents"
DEFAULT_MAX_UPLOAD_BYTES = 15 * 1024 * 1024
DEFAULT_PRESIGN_TTL_SECONDS = 300
DEFAULT_CONTRACT_TEMPLATE_KEY = (
    "templates/contracts/asiati-employment-contract-v1.docx"
)
DEFAULT_CONTRACT_TEMPLATE_MANIFEST_KEY = (
    "templates/contracts/asiati-employment-contract-v1.json"
)


@dataclass(frozen=True)
class EmployeeDocumentStorageConfig:
    bucket: str
    prefix: str = DEFAULT_PREFIX
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES
    presign_ttl_seconds: int = DEFAULT_PRESIGN_TTL_SECONDS
    contract_template_key: str = DEFAULT_CONTRACT_TEMPLATE_KEY
    contract_template_manifest_key: str = DEFAULT_CONTRACT_TEMPLATE_MANIFEST_KEY

    @classmethod
    def from_env(cls) -> "EmployeeDocumentStorageConfig":
        bucket = os.getenv("EMPLOYEE_DOCUMENTS_BUCKET", "").strip()
        if not bucket:
            raise RuntimeError("EMPLOYEE_DOCUMENTS_BUCKET is not configured")
        prefix = (
            os.getenv("EMPLOYEE_DOCUMENTS_PREFIX", DEFAULT_PREFIX)
            .strip()
            .strip("/")
            or DEFAULT_PREFIX
        )
        return cls(
            bucket=bucket,
            prefix=prefix,
            max_upload_bytes=int(
                os.getenv(
                    "EMPLOYEE_DOCUMENT_MAX_UPLOAD_BYTES",
                    str(DEFAULT_MAX_UPLOAD_BYTES),
                )
            ),
            presign_ttl_seconds=int(
                os.getenv(
                    "EMPLOYEE_DOCUMENT_PRESIGN_TTL_SECONDS",
                    str(DEFAULT_PRESIGN_TTL_SECONDS),
                )
            ),
            contract_template_key=os.getenv(
                "EMPLOYEE_CONTRACT_TEMPLATE_KEY",
                DEFAULT_CONTRACT_TEMPLATE_KEY,
            ).strip(),
            contract_template_manifest_key=os.getenv(
                "EMPLOYEE_CONTRACT_TEMPLATE_MANIFEST_KEY",
                DEFAULT_CONTRACT_TEMPLATE_MANIFEST_KEY,
            ).strip(),
        )


def generated_artifact_key(
    employee_id: str,
    document_id: str,
    artifact_id: str,
    extension: str,
) -> str:
    ext = str(extension or "").strip().lower().lstrip(".")
    return (
        f"{DEFAULT_PREFIX}/employees/{employee_id}/documents/{document_id}/"
        f"generated/{artifact_id}.{ext}"
    )


def signed_version_key(
    employee_id: str,
    document_id: str,
    version_number: int,
    version_id: str,
) -> str:
    return (
        f"{DEFAULT_PREFIX}/employees/{employee_id}/documents/{document_id}/"
        f"signed/v{int(version_number):04d}-{version_id}.pdf"
    )


class EmployeeDocumentStorage:
    def __init__(
        self,
        *,
        client=None,
        bucket: str | None = None,
        config: EmployeeDocumentStorageConfig | None = None,
    ):
        self.config = config or (
            EmployeeDocumentStorageConfig.from_env()
            if bucket is None
            else EmployeeDocumentStorageConfig(bucket=bucket)
        )
        self.bucket = bucket or self.config.bucket
        if client is None:
            region = os.getenv("AWS_REGION", "us-east-2")
            client = get_cached_session().client("s3", region_name=region)
        self.client = client

    def put_bytes(self, key: str, body: bytes, content_type: str) -> None:
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
        )

    def get_bytes(self, key: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        return response["Body"].read()

    def delete_object(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def presign_get(
        self,
        key: str,
        *,
        filename: str,
        content_type: str,
    ) -> str:
        safe_name = str(filename or "document").replace("\r", " ").replace("\n", " ")
        disposition = "attachment; filename*=UTF-8''" + quote(safe_name, safe="")
        return self.client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.bucket,
                "Key": key,
                "ResponseContentDisposition": disposition,
                "ResponseContentType": content_type,
            },
            ExpiresIn=self.config.presign_ttl_seconds,
        )
