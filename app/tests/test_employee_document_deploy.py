"""Deployment contracts for private employee document storage."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_employee_document_bucket_is_private_encrypted_versioned_and_retained():
    template_path = ROOT / "infra" / "employee-documents.yml"
    assert template_path.exists()

    template = yaml.safe_load(template_path.read_text(encoding="utf-8"))
    bucket = template["Resources"]["EmployeeDocumentsBucket"]
    props = bucket["Properties"]

    assert bucket["DeletionPolicy"] == "Retain"
    assert bucket["UpdateReplacePolicy"] == "Retain"
    assert props["BucketName"]["Fn::Sub"] == (
        "ai-recruiter-employee-documents-${AWS::AccountId}-${AWS::Region}"
    )
    assert props["VersioningConfiguration"]["Status"] == "Enabled"
    assert props["PublicAccessBlockConfiguration"] == {
        "BlockPublicAcls": True,
        "IgnorePublicAcls": True,
        "BlockPublicPolicy": True,
        "RestrictPublicBuckets": True,
    }
    encryption = props["BucketEncryption"]["ServerSideEncryptionConfiguration"]
    assert encryption[0]["ServerSideEncryptionByDefault"]["SSEAlgorithm"] == "AES256"
    assert "CorsConfiguration" not in props


def test_employee_document_runtime_policy_is_prefix_scoped():
    template = yaml.safe_load(
        (ROOT / "infra" / "employee-documents.yml").read_text(encoding="utf-8")
    )
    statements = template["Resources"]["EmployeeDocumentsBucketPolicy"][
        "Properties"
    ]["PolicyDocument"]["Statement"]

    actions = {statement["Sid"]: set(statement["Action"]) for statement in statements}
    resources = {
        statement["Sid"]: str(statement["Resource"])
        for statement in statements
    }

    assert actions["RuntimeReadContractTemplates"] == {"s3:GetObject"}
    assert actions["RuntimeManageEmployeeDocuments"] == {
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
    }
    assert "templates/contracts/*" in resources["RuntimeReadContractTemplates"]
    assert "employee-documents/*" in resources["RuntimeManageEmployeeDocuments"]


def test_api_deploy_wires_employee_document_environment():
    deploy_script = (ROOT / "scripts" / "deploy-api.sh").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(
        encoding="utf-8"
    )

    for key in (
        "EMPLOYEE_DOCUMENTS_BUCKET",
        "EMPLOYEE_DOCUMENTS_PREFIX",
        "EMPLOYEE_CONTRACT_TEMPLATE_KEY",
        "EMPLOYEE_CONTRACT_TEMPLATE_MANIFEST_KEY",
        "EMPLOYEE_DOCUMENT_MAX_UPLOAD_BYTES",
        "EMPLOYEE_DOCUMENT_PRESIGN_TTL_SECONDS",
    ):
        assert key in deploy_script
        assert key in workflow
