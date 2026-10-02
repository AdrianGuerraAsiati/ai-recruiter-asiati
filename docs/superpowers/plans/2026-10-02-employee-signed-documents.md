# Employee Signed Documents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a private employee-document subsystem that generates the initial ASIATI contract as DOCX + reference PDF, archives externally signed PDFs as immutable versions, and exposes only each employee's current signed documents to that employee.

**Architecture:** Create a focused `app/domains/employee_documents` domain with its own ORM models, service layer, template renderer, LibreOffice PDF converter, S3 adapter, and HTTP router. Store employee documents in a dedicated private/versioned S3 bucket that is never part of the candidate Bedrock Knowledge Base, while PostgreSQL remains the source of truth for lifecycle, version, ownership, audit, and integrity metadata. Reuse the existing hiring contract snapshot in `OdooContractSync.payload` for system-resolved contract values, but keep signed-document evidence independent of Odoo delivery.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, PostgreSQL, boto3/S3, python-docx, PyMuPDF, LibreOffice headless, React/Vite/Vitest, AWS CloudFormation, existing Cognito/RBAC.

**Spec:** `docs/superpowers/specs/2026-10-02-employee-signed-documents-design.md`

## Global Constraints

- AWS region is `us-east-2`.
- Signed employee documents are confidential HR records and must never use the candidate/Bedrock `documents/` prefix.
- Production storage uses a dedicated private bucket named `ai-recruiter-employee-documents-${AWS::AccountId}-${AWS::Region}`.
- S3 Block Public Access, SSE-S3 encryption, and bucket versioning are enabled.
- Signed evidence is PDF-only in this release.
- Maximum signed-PDF upload size is **15 MiB** (`15 * 1024 * 1024` bytes).
- Presigned GET URLs expire after **300 seconds** by default.
- Signed document versions are append-only; no API overwrites or physically deletes an existing signed version.
- Corrections create a new version and preserve the previous version.
- Employees can list/download only their own current signed, non-void documents.
- Admin/HR users can generate, upload, inspect history, download generated/history artifacts, and void.
- The initial contract template is fixed and controlled; there is no end-user template editor.
- The legal wording must come from the approved ASIATI source PDF. If the approved source PDF has not been supplied, do **not** fabricate a production legal template.
- The production template is stored privately at `templates/contracts/asiati-employment-contract-v1.docx` with manifest `templates/contracts/asiati-employment-contract-v1.json`.
- DOCX placeholders must live wholly inside a single Word run so replacements preserve surrounding formatting.
- DOCX→PDF conversion uses `libreoffice --headless` inside the backend container with a **30-second** process timeout.
- Odoo does not receive signed PDF binaries in this MVP.
- Odoo failure must not block document archival.
- Hiring must not fail because template rendering or PDF conversion fails.
- Existing candidate, hiring, onboarding, training, Odoo, and Talent ID behavior must remain compatible.
- Alembic remains the only production schema owner; the next migration revision is `039`.

## Review Focus

1. **IDOR / guessed document IDs:** an employee requesting another employee's document or a historical version must receive no document metadata or download URL. Task 5 adds explicit API tests for cross-employee IDs and historical-version guessing.
2. **Concurrent signed uploads:** two uploads racing for the same document must produce distinct monotonically increasing versions and exactly one current version. Task 3 adds a PostgreSQL two-session concurrency test around the document row lock.
3. **Fake/malformed PDF with `application/pdf`:** MIME alone must not be trusted; invalid headers or unreadable PDFs must return 422 and create no version/S3 object. Task 3 tests both spoofed MIME and truncated PDF bytes.
4. **Partial persistence after S3 success:** if DB commit fails after an upload, the newly written object must be deleted/reconciled and no version may appear current. Task 3 injects a commit failure and asserts storage cleanup.
5. **DOCX→PDF/template failure:** a missing variable, split placeholder, LibreOffice timeout, or conversion failure must leave the logical document recoverable and must not set `PENDING_SIGNATURE` with only one generated artifact. Task 4 tests missing variables, split placeholders, timeout, and second-upload failure.

---

### Task 1: Domain schema, migration, and RBAC catalog

**Files:**
- Create: `app/domains/employee_documents/__init__.py`
- Create: `app/domains/employee_documents/models.py`
- Create: `app/migrations/versions/039_employee_documents.py`
- Modify: `app/models.py`
- Modify: `app/access_control.py`
- Modify: `app/tests/test_postgres_migrations.py`
- Modify: `app/tests/test_rbac.py`
- Create: `app/tests/test_employee_document_models.py`

**Interfaces:**
- Consumes: existing `UserProfile`, `JobCandidate`, and `OdooContractSync` tables.
- Produces:
  - `EmployeeDocument`
  - `EmployeeDocumentArtifact`
  - `EmployeeDocumentVersion`
  - permission codes:
    - `employee_documents.read_own`
    - `employee_documents.read_all`
    - `employee_documents.generate`
    - `employee_documents.upload_signed`
    - `employee_documents.manage`
    - `employee_documents.download_history`

- [ ] **Step 1: Write failing model and migration tests**

Add tests asserting:

```python
def test_employee_document_models_register_expected_tables():
    assert "employee_documents" in Base.metadata.tables
    assert "employee_document_artifacts" in Base.metadata.tables
    assert "employee_document_versions" in Base.metadata.tables


def test_employee_role_only_gets_own_document_permission(db):
    principal = resolve_principal(
        db,
        {"sub": "employee-docs-1", "email": "employee.docs@asiati.com.co"},
    )
    assert "employee_documents.read_own" in principal["permissions"]
    assert "employee_documents.read_all" not in principal["permissions"]
    assert "employee_documents.upload_signed" not in principal["permissions"]
```

Extend PostgreSQL migration smoke expectations to revision `039`, all three new tables, and unique `(document_id, version_number)`.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
pytest app/tests/test_employee_document_models.py app/tests/test_rbac.py -q
```

Expected: FAIL because employee-document models/permissions do not exist.

- [ ] **Step 3: Implement focused ORM models**

In `app/domains/employee_documents/models.py`, create:

```python
class EmployeeDocument(Base): ...
class EmployeeDocumentArtifact(Base): ...
class EmployeeDocumentVersion(Base): ...
```

Pinned values:

- `EmployeeDocument.document_type`: `CONTRACT | ADDENDUM | OTHER`
- `EmployeeDocument.status`: `DRAFT | PENDING_SIGNATURE | SIGNED | VOID`
- `EmployeeDocumentArtifact.artifact_kind`: `GENERATED_DOCX | REFERENCE_PDF`
- `EmployeeDocument.contract_sync_id`: nullable FK to `odoo_contract_syncs.id`, unique when non-null
- `EmployeeDocument.source_job_candidate_id`: nullable FK to `job_candidates.id`
- `EmployeeDocument.current_signed_version_id`: nullable FK to `employee_document_versions.id` using an explicitly named deferred/use-alter FK to break the parent/child creation cycle
- `EmployeeDocumentVersion.superseded_by_version_id`: nullable self-FK
- unique version constraint: `uq_employee_document_versions_document_version`
- indexes:
  - `idx_employee_documents_employee_status`
  - `idx_employee_document_artifacts_document_created`
  - `idx_employee_document_versions_document_created`

Keep these models in the domain file and re-export them from `app/models.py` like Odoo/training domain models.

- [ ] **Step 4: Add Alembic revision `039`**

Create all three tables and constraints without modifying `038`.

Migration order:

1. `employee_documents` without the circular current-version FK.
2. `employee_document_artifacts`.
3. `employee_document_versions`.
4. Add named FK from `employee_documents.current_signed_version_id` to `employee_document_versions.id`.

Downgrade reverses the FK then tables.

- [ ] **Step 5: Add RBAC permissions**

Add all six permission definitions to `PERMISSION_DEFINITIONS`.

Because `_ADMIN_PERMISSIONS = set(PERMISSION_DEFINITIONS)`, ADMIN receives all six automatically.

Add only `employee_documents.read_own` to `_EMPLOYEE_PERMISSIONS`.

- [ ] **Step 6: Run model/RBAC tests**

Run:

```bash
pytest app/tests/test_employee_document_models.py app/tests/test_rbac.py -q
```

Expected: PASS.

- [ ] **Step 7: Run PostgreSQL migration smoke**

Run in the same PostgreSQL environment used by CI:

```bash
pytest app/tests/test_postgres_migrations.py -q
```

Expected: PASS with Alembic revision `039`.

- [ ] **Step 8: Commit**

```bash
git add app/domains/employee_documents app/migrations/versions/039_employee_documents.py app/models.py app/access_control.py app/tests/test_employee_document_models.py app/tests/test_rbac.py app/tests/test_postgres_migrations.py
git commit -m "feat: add employee document domain schema"
```

---

### Task 2: Private S3 storage boundary and deployment configuration

**Files:**
- Create: `app/domains/employee_documents/storage.py`
- Create: `infra/employee-documents.yml`
- Modify: `.github/workflows/deploy.yml`
- Modify: `scripts/deploy-api.sh`
- Create: `app/tests/test_employee_document_storage.py`
- Create: `app/tests/test_employee_document_deploy.py`

**Interfaces:**
- Consumes: AWS runtime credentials already exposed to the backend container.
- Produces:
  - `EmployeeDocumentStorageConfig.from_env() -> EmployeeDocumentStorageConfig`
  - `EmployeeDocumentStorage.put_bytes(key: str, body: bytes, content_type: str) -> None`
  - `EmployeeDocumentStorage.get_bytes(key: str) -> bytes`
  - `EmployeeDocumentStorage.delete_object(key: str) -> None`
  - `EmployeeDocumentStorage.presign_get(key: str, filename: str, content_type: str) -> str`
  - `generated_artifact_key(employee_id: str, document_id: str, artifact_id: str, extension: str) -> str`
  - `signed_version_key(employee_id: str, document_id: str, version_number: int, version_id: str) -> str`

- [ ] **Step 1: Write failing storage tests**

Tests pin:

```python
def test_signed_keys_never_use_candidate_documents_prefix():
    key = signed_version_key("emp-1", "doc-1", 2, "ver-2")
    assert key == (
        "employee-documents/employees/emp-1/documents/doc-1/"
        "signed/v0002-ver-2.pdf"
    )
    assert not key.startswith("documents/")


def test_presign_uses_300_second_default(fake_s3):
    storage = EmployeeDocumentStorage(client=fake_s3, bucket="private-bucket")
    storage.presign_get(
        "employee-documents/x.pdf",
        filename="Contrato firmado.pdf",
        content_type="application/pdf",
    )
    assert fake_s3.presign_calls[0]["ExpiresIn"] == 300
```

Deployment contract tests assert:

- CloudFormation bucket has Public Access Block, AES256 encryption, Versioning Enabled, Retain policies.
- runtime role has object access only for `templates/contracts/*` and `employee-documents/*`.
- deploy workflow exports `EMPLOYEE_DOCUMENTS_BUCKET`, `EMPLOYEE_DOCUMENTS_PREFIX`, `EMPLOYEE_CONTRACT_TEMPLATE_KEY`, `EMPLOYEE_CONTRACT_TEMPLATE_MANIFEST_KEY`, `EMPLOYEE_DOCUMENT_MAX_UPLOAD_BYTES`, `EMPLOYEE_DOCUMENT_PRESIGN_TTL_SECONDS`.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
pytest app/tests/test_employee_document_storage.py app/tests/test_employee_document_deploy.py -q
```

Expected: FAIL because storage module/infrastructure do not exist.

- [ ] **Step 3: Implement storage adapter**

Use a lazily cached boto3 S3 client configured for `AWS_REGION`, defaulting to `us-east-2`. Allow client injection for tests.

Pinned defaults:

```text
EMPLOYEE_DOCUMENTS_PREFIX=employee-documents
EMPLOYEE_DOCUMENT_MAX_UPLOAD_BYTES=15728640
EMPLOYEE_DOCUMENT_PRESIGN_TTL_SECONDS=300
EMPLOYEE_CONTRACT_TEMPLATE_KEY=templates/contracts/asiati-employment-contract-v1.docx
EMPLOYEE_CONTRACT_TEMPLATE_MANIFEST_KEY=templates/contracts/asiati-employment-contract-v1.json
```

Do not reuse `S3_BUCKET` from candidate CV ingestion.

`presign_get` sets `ResponseContentDisposition` to an attachment filename and does not log the returned URL.

- [ ] **Step 4: Add dedicated CloudFormation bucket**

Create `infra/employee-documents.yml` modeled after the existing private training bucket, but without browser upload CORS.

Bucket:

```text
ai-recruiter-employee-documents-${AWS::AccountId}-${AWS::Region}
```

Runtime policy actions:

- templates: `s3:GetObject`
- employee documents: `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject`

`DeleteObject` exists only for generated-artifact replacement and rollback/orphan cleanup; no signed-version delete API will expose it.

- [ ] **Step 5: Wire deploy environment**

Pass the new variables into the API container through the existing deployment workflow/script. Do not add them to the worker unless a later task moves generation to the worker.

- [ ] **Step 6: Run storage/deploy tests**

Run:

```bash
pytest app/tests/test_employee_document_storage.py app/tests/test_employee_document_deploy.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add app/domains/employee_documents/storage.py infra/employee-documents.yml .github/workflows/deploy.yml scripts/deploy-api.sh app/tests/test_employee_document_storage.py app/tests/test_employee_document_deploy.py
git commit -m "feat: add private employee document storage"
```

---

### Task 3: Signed-document lifecycle, PDF validation, and immutable versions

**Files:**
- Create: `app/domains/employee_documents/schemas.py`
- Create: `app/domains/employee_documents/service.py`
- Create: `app/tests/test_employee_documents_service.py`
- Create: `app/tests/test_employee_documents_postgres.py`

**Interfaces:**
- Consumes: Task 1 ORM models; Task 2 `EmployeeDocumentStorage`.
- Produces:
  - `create_document(db: Session, *, employee_id: str, document_type: str, title: str, created_by_sub: str, contract_sync_id: str | None = None, source_job_candidate_id: str | None = None) -> EmployeeDocument`
  - `ensure_initial_contract_document(db: Session, *, employee_id: str, created_by_sub: str) -> EmployeeDocument`
  - `append_signed_version(db: Session, *, employee_id: str, document_id: str, file_bytes: bytes, original_filename: str, uploaded_by_sub: str, signed_at: datetime | None, storage: EmployeeDocumentStorage) -> EmployeeDocumentVersion`
  - `void_document(db: Session, *, employee_id: str, document_id: str, reason: str, actor_sub: str) -> EmployeeDocument`
  - `list_documents_for_hr(db: Session, *, employee_id: str) -> list[EmployeeDocument]`
  - `list_current_signed_for_employee(db: Session, *, employee_id: str) -> list[EmployeeDocument]`
  - `document_payload(document: EmployeeDocument, *, include_history: bool = False) -> dict`
  - domain exceptions: `EmployeeDocumentNotFound`, `EmployeeDocumentValidationError`, `EmployeeDocumentStateError`, `EmployeeDocumentStorageError`

- [ ] **Step 1: Write failing lifecycle tests**

Cover:

```python
def test_second_signed_upload_creates_v2_without_mutating_v1(...):
    first = append_signed_version(...)
    second = append_signed_version(...)
    assert first.version_number == 1
    assert second.version_number == 2
    assert first.storage_key != second.storage_key
    assert document.current_signed_version_id == second.id
    assert first.superseded_by_version_id == second.id


def test_spoofed_pdf_is_rejected_before_storage(...):
    with pytest.raises(EmployeeDocumentValidationError):
        append_signed_version(
            ...,
            file_bytes=b"%PDF-not-a-real-document",
            original_filename="signed.pdf",
        )
    assert storage.put_calls == []
```

Use PyMuPDF to validate readability/page count after checking the `%PDF-` signature.

Also test:

- >15 MiB rejected;
- empty PDF rejected;
- `VOID` document rejects new signed version;
- SHA-256 equals `hashlib.sha256(file_bytes).hexdigest()`;
- employee list returns only `SIGNED` + non-void + current version;
- HR list preserves historical metadata.

- [ ] **Step 2: Run service tests and verify RED**

Run:

```bash
pytest app/tests/test_employee_documents_service.py -q
```

Expected: FAIL because service does not exist.

- [ ] **Step 3: Implement logical document creation and initial-contract idempotency**

`ensure_initial_contract_document` locates the employee's `OdooContractSync`. If none exists, raise a validation error explaining that structured contract data is not available.

Use `contract_sync_id` uniqueness to make repeated calls idempotent.

Title default for the initial contract: `Contrato laboral`.

- [ ] **Step 4: Implement signed-PDF validation**

Validation order:

1. non-empty;
2. byte size ≤ configured max;
3. filename normalized only for display, never for S3 key;
4. starts with `%PDF-`;
5. PyMuPDF opens successfully and `page_count > 0`.

Do not log file contents.

- [ ] **Step 5: Implement transactional immutable version append**

Inside `append_signed_version`:

1. lock the logical `EmployeeDocument` row using `SELECT ... FOR UPDATE`;
2. derive next version from the max existing version;
3. pre-allocate UUID/version-specific S3 key;
4. upload bytes;
5. add immutable version row;
6. mark previous current version's `superseded_at` + `superseded_by_version_id`;
7. point parent `current_signed_version_id` to new version;
8. set parent `status = "SIGNED"`;
9. commit.

If DB persistence fails after S3 upload: rollback then call `storage.delete_object(new_key)`, then re-raise a sanitized domain error.

There is no update/delete method for signed versions.

- [ ] **Step 6: Add PostgreSQL concurrency test**

Using two independent sessions against the CI PostgreSQL database, race two `append_signed_version` calls for the same document.

Assert:

```python
assert sorted(v.version_number for v in versions) == [1, 2]
assert sum(v.id == document.current_signed_version_id for v in versions) == 1
```

This test may skip only when `DATABASE_URL` is not PostgreSQL.

- [ ] **Step 7: Run service + PostgreSQL tests**

Run:

```bash
pytest app/tests/test_employee_documents_service.py app/tests/test_employee_documents_postgres.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add app/domains/employee_documents/schemas.py app/domains/employee_documents/service.py app/tests/test_employee_documents_service.py app/tests/test_employee_documents_postgres.py
git commit -m "feat: add immutable signed document lifecycle"
```

---

### Task 4: Fixed template manifest, DOCX rendering, and reference PDF conversion

**Files:**
- Create: `app/domains/employee_documents/template.py`
- Create: `app/domains/employee_documents/converter.py`
- Create: `app/domains/employee_documents/generation.py`
- Modify: `Dockerfile`
- Create: `app/tests/fixtures/employee_documents/build_test_template.py`
- Create: `app/tests/test_employee_document_generation.py`
- Modify: `app/tests/test_employee_document_deploy.py`

**Interfaces:**
- Consumes: Task 2 storage; Task 3 document lifecycle; `OdooContractSync.payload`.
- Produces:
  - `TemplateManifest.from_json_bytes(data: bytes) -> TemplateManifest`
  - `resolve_contract_generation_context(db: Session, *, employee_id: str, document_id: str, storage: EmployeeDocumentStorage) -> dict`
  - `render_docx(template_bytes: bytes, *, variables: dict[str, str], manifest: TemplateManifest) -> bytes`
  - `convert_docx_to_pdf(docx_bytes: bytes, *, timeout_seconds: int = 30) -> bytes`
  - `generate_contract_artifacts(db: Session, *, employee_id: str, document_id: str, manual_values: dict[str, str], actor_sub: str, storage: EmployeeDocumentStorage) -> tuple[EmployeeDocumentArtifact, EmployeeDocumentArtifact]`
  - exceptions: `TemplateNotConfigured`, `TemplateValidationError`, `MissingTemplateVariables`, `DocumentConversionError`

- [ ] **Step 1: Define and test manifest contract**

The fixed template manifest JSON has this schema:

```json
{
  "template_version": "1",
  "document_type": "CONTRACT",
  "fields": [
    {
      "name": "employee_full_name",
      "label": "Nombre completo",
      "source": "employee.full_name",
      "required": true
    },
    {
      "name": "employee_document_number",
      "label": "Documento de identidad",
      "source": "manual",
      "required": true
    }
  ]
}
```

Allowed `source` values in v1:

- `employee.full_name`
- `employee.job_title`
- `employee.department`
- `employee.email`
- `contract.contract_type`
- `contract.start_date`
- `contract.end_date`
- `contract.monthly_wage`
- `manual`

Unknown sources are rejected.

The actual production manifest is finalized only from the approved ASIATI PDF; tests use a synthetic fixture manifest.

- [ ] **Step 2: Write failing renderer/converter tests**

Cover:

```python
def test_render_docx_replaces_single_run_placeholders_and_preserves_text(...):
    rendered = render_docx(
        fixture_template,
        variables={"employee_full_name": "Ana Pérez"},
        manifest=manifest,
    )
    assert "{{ employee_full_name }}" not in extract_all_docx_text(rendered)
    assert "Ana Pérez" in extract_all_docx_text(rendered)


def test_render_docx_rejects_placeholder_split_across_runs(...):
    with pytest.raises(TemplateValidationError):
        render_docx(split_run_template, variables=..., manifest=manifest)


def test_missing_required_manual_field_does_not_generate(...):
    with pytest.raises(MissingTemplateVariables) as error:
        generate_contract_artifacts(..., manual_values={})
    assert "employee_document_number" in error.value.fields
```

Mock `subprocess.run` to test:

- `libreoffice --headless --convert-to pdf --outdir ...`;
- timeout converts to `DocumentConversionError`;
- missing output PDF converts to `DocumentConversionError`.

Add failure test where DOCX upload succeeds and PDF upload fails; the DOCX upload is deleted and DB remains `DRAFT`.

- [ ] **Step 3: Run generation tests and verify RED**

Run:

```bash
pytest app/tests/test_employee_document_generation.py -q
```

Expected: FAIL because generator/converter do not exist.

- [ ] **Step 4: Implement manifest and context resolver**

Load template + manifest through Task 2 storage.

System fields come from:

- `UserProfile`;
- `OdooContractSync.payload["contract"]`.

Manual fields come only from `manual_values` and only when the manifest declares `source = "manual"`.

Return a safe context payload that tells UI:

- template version;
- resolved field values;
- manual fields/labels;
- missing required fields.

Do not return the template binary.

- [ ] **Step 5: Implement DOCX renderer**

Walk:

- body paragraphs;
- table cells recursively;
- section headers;
- section footers.

Replace placeholders only when the entire token `{{ field_name }}` exists in one run. If a placeholder is visible in paragraph text but split across runs, raise `TemplateValidationError` instead of flattening the paragraph and losing formatting.

After rendering, scan for undeclared/unresolved `{{ ... }}` tokens; reject if any remain.

- [ ] **Step 6: Implement LibreOffice converter**

Use `tempfile.TemporaryDirectory`, write `source.docx`, run:

```text
libreoffice --headless --convert-to pdf --outdir <tempdir> <source.docx>
```

with `timeout=30`, captured stdout/stderr, and no shell.

Read `source.pdf`; verify it starts with `%PDF-` and opens through PyMuPDF before returning bytes.

- [ ] **Step 7: Install LibreOffice in backend image**

Update `Dockerfile` before Python dependency installation:

```dockerfile
RUN apt-get update \
    && apt-get install -y --no-install-recommends libreoffice-writer fonts-liberation \
    && rm -rf /var/lib/apt/lists/*
```

Extend deploy contract test to assert these packages and `libreoffice` command support exist in the image definition.

- [ ] **Step 8: Implement atomic generated-artifact persistence**

Generate DOCX and PDF fully in memory before persistence.

Upload both unique generated keys. Insert exactly one active `GENERATED_DOCX` and one active `REFERENCE_PDF` record for the logical document; after successful commit, delete superseded **generated** objects/rows.

Only after both artifacts and DB metadata succeed set document status to `PENDING_SIGNATURE`.

Signed version rows are never touched by regeneration.

- [ ] **Step 9: Run generation/deploy tests**

Run:

```bash
pytest app/tests/test_employee_document_generation.py app/tests/test_employee_document_deploy.py -q
```

Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add app/domains/employee_documents/template.py app/domains/employee_documents/converter.py app/domains/employee_documents/generation.py Dockerfile app/tests/fixtures/employee_documents app/tests/test_employee_document_generation.py app/tests/test_employee_document_deploy.py
git commit -m "feat: generate employee contract documents"
```

---

### Task 5: HR and employee document APIs plus hiring handoff

**Files:**
- Create: `app/domains/employee_documents/router.py`
- Modify: `app/bootstrap.py`
- Modify: `app/domains/hiring/service.py`
- Modify: `app/tests/test_hiring.py`
- Create: `app/tests/test_employee_documents_api.py`

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces HR routes:
  - `GET /api/employees/{employee_id}/documents`
  - `POST /api/employees/{employee_id}/documents/contracts`
  - `POST /api/employees/{employee_id}/documents`
  - `GET /api/employees/{employee_id}/documents/{document_id}/generation-context`
  - `POST /api/employees/{employee_id}/documents/{document_id}/generate`
  - `POST /api/employees/{employee_id}/documents/{document_id}/signed-versions`
  - `GET /api/employees/{employee_id}/documents/{document_id}/versions`
  - `POST /api/employees/{employee_id}/documents/{document_id}/artifacts/{artifact_id}/download`
  - `POST /api/employees/{employee_id}/documents/{document_id}/versions/{version_id}/download`
  - `POST /api/employees/{employee_id}/documents/{document_id}/void`
- Produces self-service routes:
  - `GET /api/me/documents`
  - `POST /api/me/documents/{document_id}/download`

- [ ] **Step 1: Write failing permission/API tests**

Test exact permission boundaries:

```python
def test_employee_me_documents_only_returns_own_current_signed(...):
    response = employee_client.get("/api/me/documents")
    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == ["own-current-doc"]


def test_employee_cannot_download_guessed_other_employee_document(...):
    response = employee_client.post(
        "/api/me/documents/other-employees-document/download"
    )
    assert response.status_code == 404
    assert "download_url" not in response.text


def test_employee_cannot_download_historical_version_by_hr_route(...):
    response = employee_client.post(
        f"/api/employees/{employee_id}/documents/{doc_id}/versions/{old_version}/download"
    )
    assert response.status_code == 403
```

Also cover HR generation, signed upload, history, void, and URL TTL response.

- [ ] **Step 2: Run API tests and verify RED**

Run:

```bash
pytest app/tests/test_employee_documents_api.py -q
```

Expected: FAIL because routes are absent.

- [ ] **Step 3: Implement HR routers with explicit permissions**

Map permissions:

- list: `employee_documents.read_all`
- contract create/context/generate: `employee_documents.generate`
- signed upload: `employee_documents.upload_signed`
- history/history download: `employee_documents.download_history`
- void/create ADDENDUM|OTHER: `employee_documents.manage`

Signed upload is multipart:

- `file: UploadFile`
- optional `signed_at: datetime = Form(None)`

Read at most `max_upload_bytes + 1` and reject overflow before service invocation.

`POST /documents` accepts only `ADDENDUM` or `OTHER`; initial `CONTRACT` uses the idempotent contract route.

Generation is allowed only for `CONTRACT` in v1. ADDENDUM/OTHER can be archived as signed PDFs but have no invented generic legal template.

- [ ] **Step 4: Implement self-service routes**

Resolve employee ID exclusively from:

```python
principal["profile"]["id"]
```

Never accept an arbitrary employee ID in self-service routes.

`/api/me/documents` returns only current signed, non-void document metadata.

Download resolves only `document.current_signed_version_id` after ownership/status checks.

Return:

```json
{
  "download_url": "<presigned>",
  "expires_in": 300,
  "filename": "..."
}
```

No permanent S3 URL is stored or returned.

- [ ] **Step 5: Register routers in app bootstrap**

Add both HR and self-service routers to `create_app()`.

- [ ] **Step 6: Add recoverable hiring handoff**

After the existing structured contract outbox has been prepared and the hiring transaction is durable, call:

```python
ensure_initial_contract_document(
    db,
    employee_id=employee.id,
    created_by_sub=created_by_sub,
)
```

in a separate recoverable block.

If document preparation fails:

- rollback only that document-preparation attempt;
- keep employee/application/onboarding/Odoo outboxes intact;
- return `employee_document: null`;
- allow the HR contract endpoint to create it idempotently later.

Do **not** render DOCX/PDF inside `hire_candidate`.

On success include a compact `employee_document` payload in the hiring response.

- [ ] **Step 7: Extend hiring tests**

Add:

```python
def test_hire_with_contract_prepares_recoverable_document_record(...):
    result = hire_candidate(..., contract={...})
    assert result["employee_document"]["document_type"] == "CONTRACT"
    assert result["employee_document"]["status"] == "DRAFT"


def test_document_preparation_failure_does_not_rollback_hiring(...):
    ...
    assert result["application_status"] == "HIRED"
    assert result["employee"]["id"]
    assert result["employee_document"] is None
```

- [ ] **Step 8: Run API + hiring tests**

Run:

```bash
pytest app/tests/test_employee_documents_api.py app/tests/test_hiring.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add app/domains/employee_documents/router.py app/bootstrap.py app/domains/hiring/service.py app/tests/test_employee_documents_api.py app/tests/test_hiring.py
git commit -m "feat: expose employee document workflows"
```

---

### Task 6: HR document management UI in Employees

**Files:**
- Create: `frontend-react/src/features/employee-documents/EmployeeDocumentsPanel.jsx`
- Create: `frontend-react/src/features/employee-documents/employee-documents.css`
- Modify: `frontend-react/src/pages/Employees.jsx`
- Modify: `frontend-react/src/__tests__/Employees.test.jsx`
- Create: `frontend-react/src/__tests__/EmployeeDocumentsPanel.test.jsx`

**Interfaces:**
- Consumes Task 5 HR API routes.
- Produces `EmployeeDocumentsPanel({ employee, open, onClose })`.

- [ ] **Step 1: Write failing HR UI tests**

Mock APIs and assert:

```jsx
expect(screen.getByRole("heading", { name: /documentos de ana pérez/i })).toBeInTheDocument();
expect(screen.getByText("Contrato laboral")).toBeInTheDocument();
expect(screen.getByText("Pendiente de firma")).toBeInTheDocument();
```

Actions by state:

- DRAFT: `Preparar documento`
- PENDING_SIGNATURE: `Descargar DOCX`, `Descargar PDF de referencia`, `Subir PDF firmado`
- SIGNED: `Descargar firmado`, `Subir nueva versión`, `Ver historial`
- VOID: history only for authorized HR users

Test upload confirmation includes wording equivalent to:

> Se creará una nueva versión. La versión firmada anterior se conservará en el historial.

- [ ] **Step 2: Run frontend tests and verify RED**

Run:

```bash
cd frontend-react
npm test -- --run src/__tests__/EmployeeDocumentsPanel.test.jsx src/__tests__/Employees.test.jsx
```

Expected: FAIL because panel/action is absent.

- [ ] **Step 3: Add Documents action to employee rows**

In `Employees.jsx`, show `Documentos` only when `hasPermission("employee_documents.read_all")`.

Opening it sets the selected employee and renders `EmployeeDocumentsPanel`; do not load documents for every employee in the directory list.

- [ ] **Step 4: Implement HR panel loading and lifecycle states**

Panel loads:

```text
GET /employees/{employee_id}/documents
```

Use existing `LoadingState`, `EmptyState`, `FeedbackMessage`, and button conventions.

For a hired employee with no initial contract record, expose `Crear contrato documental` which calls the idempotent contract route.

- [ ] **Step 5: Implement generation context/manual fields**

Before generation, load `generation-context`.

Display:

- system-resolved fields as read-only summary;
- manifest `manual` fields as labeled inputs.

Submit only manual field values to the generate endpoint.

If template is not configured, display a controlled HR error; do not offer a blank-document workaround.

- [ ] **Step 6: Implement download and signed upload**

For download endpoints, receive the short-lived URL then trigger browser navigation/download; do not persist URL in React state beyond the action.

Signed upload:

- accept `.pdf`;
- client-side 15 MiB guard for UX;
- backend remains authoritative validator;
- optional signed date;
- immutable-version confirmation before upload.

- [ ] **Step 7: Implement history/void UI**

History displays:

- version number;
- signed date when available;
- upload timestamp;
- uploader identifier only for HR;
- SHA-256 shortened visually but full value available via title/copy;
- current/superseded state.

Void requires a non-empty reason and confirmation.

- [ ] **Step 8: Run frontend tests**

Run:

```bash
cd frontend-react
npm test -- --run src/__tests__/EmployeeDocumentsPanel.test.jsx src/__tests__/Employees.test.jsx
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add frontend-react/src/features/employee-documents frontend-react/src/pages/Employees.jsx frontend-react/src/__tests__/EmployeeDocumentsPanel.test.jsx frontend-react/src/__tests__/Employees.test.jsx
git commit -m "feat: manage employee documents from HR"
```

---

### Task 7: Employee self-service “Mis documentos”

**Files:**
- Create: `frontend-react/src/pages/MyDocuments.jsx`
- Modify: `frontend-react/src/App.jsx`
- Modify: `frontend-react/src/components/Navbar.jsx`
- Modify: `frontend-react/src/components/Layout.jsx`
- Modify: `frontend-react/src/ui-system.css`
- Create: `frontend-react/src/__tests__/MyDocuments.test.jsx`
- Create or modify the existing navigation test file that covers `Navbar`

**Interfaces:**
- Consumes Task 5 self-service routes.
- Produces protected route `/documents` requiring `employee_documents.read_own`.

- [ ] **Step 1: Write failing employee portal tests**

Assert:

```jsx
expect(api.get).toHaveBeenCalledWith("/me/documents");
expect(screen.getByText("Contrato laboral")).toBeInTheDocument();
expect(screen.queryByText(/historial/i)).not.toBeInTheDocument();
expect(screen.queryByText(/docx/i)).not.toBeInTheDocument();
```

Clicking `Descargar PDF` calls only:

```text
POST /me/documents/{document_id}/download
```

Test that an API response containing only current signed documents produces no draft/history affordance.

- [ ] **Step 2: Run portal tests and verify RED**

Run:

```bash
cd frontend-react
npm test -- --run src/__tests__/MyDocuments.test.jsx
```

Expected: FAIL because page/route do not exist.

- [ ] **Step 3: Implement `MyDocuments` page**

Page copy focuses on employee self-service, not HR internals.

Show only:

- title/type;
- signed/current state;
- effective/signed date when available;
- download button.

Do not render:

- generated DOCX;
- reference PDF;
- historical versions;
- uploader;
- Odoo state;
- hashes;
- internal notes.

- [ ] **Step 4: Add protected route and navigation**

`App.jsx`:

```jsx
<Route
  path="/documents"
  element={
    <ProtectedPage permission="employee_documents.read_own">
      <MyDocuments />
    </ProtectedPage>
  }
/>
```

`Navbar.jsx`: add `Mis documentos` under `Cuenta`, permission `employee_documents.read_own`, `roles: ["EMPLOYEE"]`.

`Layout.jsx`: add page title `"/documents": "Mis documentos"`.

- [ ] **Step 5: Run page/navigation tests**

Run the targeted self-service and navigation tests.

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend-react/src/pages/MyDocuments.jsx frontend-react/src/App.jsx frontend-react/src/components/Navbar.jsx frontend-react/src/components/Layout.jsx frontend-react/src/ui-system.css frontend-react/src/__tests__
git commit -m "feat: add employee document self service"
```

---

### Task 8: Production template handoff, operations guide, and end-to-end verification

**Files:**
- Create: `docs/employee-documents-operations.md`
- Modify: `infra/README.md`
- Modify: `app/tests/test_employee_document_deploy.py`
- Production S3 objects, not repository files:
  - `templates/contracts/asiati-employment-contract-v1.docx`
  - `templates/contracts/asiati-employment-contract-v1.json`

**Interfaces:**
- Consumes all previous tasks plus the approved text-selectable ASIATI contract PDF.
- Produces a deployable operational procedure and installed template version 1.

- [ ] **Step 1: Write failing operations/deploy contract assertions**

Assert docs/infrastructure describe:

- dedicated bucket creation;
- exact environment variables;
- template keys/version;
- template upload procedure;
- rollback behavior;
- verification that candidate Bedrock data source does **not** point to the employee-documents bucket/prefix;
- no Odoo signed-binary synchronization;
- S3 retention warning.

- [ ] **Step 2: Run deploy contract test and verify RED**

Run:

```bash
pytest app/tests/test_employee_document_deploy.py -q
```

Expected: FAIL until runbook is complete.

- [ ] **Step 3: Reconstruct template v1 from the approved corporate PDF**

This step has one hard external prerequisite: the approved ASIATI PDF must be available to the implementer.

Rules:

- copy wording exactly from the approved source;
- do not rewrite clauses;
- preserve corporate layout as closely as practical in DOCX;
- replace variable values with manifest placeholders;
- ensure every placeholder is entirely within a single Word run;
- create manifest field labels/sources matching the exact template;
- manually compare generated reference PDF against the source layout.

If the approved PDF is unavailable, record this task as **blocked external dependency** and do not create a fake production contract. All platform/storage/archive work from Tasks 1–7 can still be completed and tested with synthetic fixtures.

- [ ] **Step 4: Upload production template + manifest to the private bucket**

Upload to:

```text
templates/contracts/asiati-employment-contract-v1.docx
templates/contracts/asiati-employment-contract-v1.json
```

Do not place the template in the candidate CV bucket/prefix.

- [ ] **Step 5: Document production deployment**

Runbook includes CloudFormation deployment to `us-east-2`, environment wiring, template install, and rollback.

It must explicitly say that signed files are retained even when a document is voided in Talent.

- [ ] **Step 6: Run backend targeted suite**

Run:

```bash
pytest   app/tests/test_employee_document_models.py   app/tests/test_employee_document_storage.py   app/tests/test_employee_documents_service.py   app/tests/test_employee_documents_postgres.py   app/tests/test_employee_document_generation.py   app/tests/test_employee_documents_api.py   app/tests/test_employee_document_deploy.py   app/tests/test_hiring.py   app/tests/test_rbac.py   app/tests/test_postgres_migrations.py -q
```

Expected: PASS, with PostgreSQL-specific tests executing in CI.

- [ ] **Step 7: Run frontend targeted suite**

Run:

```bash
cd frontend-react
npm test -- --run   src/__tests__/EmployeeDocumentsPanel.test.jsx   src/__tests__/MyDocuments.test.jsx   src/__tests__/Employees.test.jsx
npm run lint
npm run build
```

Expected: all PASS.

- [ ] **Step 8: Run full project verification**

Run the same backend/frontend commands enforced by `.github/workflows/ci.yml`, then inspect CodeQL/security workflows on the branch/PR.

Expected: green CI with no regression in candidate/hiring/onboarding behavior.

- [ ] **Step 9: Perform one controlled end-to-end test**

Using a clearly identified test employee:

1. ensure structured contract data exists;
2. create/resolve `Contrato laboral`;
3. generate DOCX + reference PDF;
4. inspect both outputs;
5. upload a harmless test signed PDF;
6. verify version 1 + SHA-256;
7. upload corrected test PDF;
8. verify version 2 current and version 1 retained;
9. log in as that employee and confirm only version 2 is exposed;
10. verify another employee cannot resolve/download it.

Do not use a real employee's legal document for the first technical smoke test.

- [ ] **Step 10: Commit**

```bash
git add docs/employee-documents-operations.md infra/README.md app/tests/test_employee_document_deploy.py
git commit -m "docs: add employee document operations"
```

---

## Final verification checklist

Before merge:

- [ ] Alembic head is `039`.
- [ ] ADMIN has all six employee-document permissions.
- [ ] EMPLOYEE has only `employee_documents.read_own`.
- [ ] No employee-document key begins with `documents/`.
- [ ] Dedicated S3 bucket is private, encrypted, versioned, retained.
- [ ] Signed PDF validation checks bytes, not only MIME/extension.
- [ ] Signed versions are append-only.
- [ ] Concurrency test proves unique ordered versions/current selection.
- [ ] DB-failure cleanup removes newly orphaned S3 writes.
- [ ] Template failure cannot create a partially prepared document state.
- [ ] LibreOffice exists in backend image and conversion errors are sanitized.
- [ ] Hiring does not render documents and survives document-preparation failure.
- [ ] HR can generate/download/upload/history/void.
- [ ] Employee can only list/download own current signed documents.
- [ ] Generated DOCX/reference PDF and history are not visible to employee.
- [ ] Odoo receives no signed PDF binary.
- [ ] Bedrock candidate KB has no access/path to employee document storage.
- [ ] Full backend/frontend CI and CodeQL are green.
