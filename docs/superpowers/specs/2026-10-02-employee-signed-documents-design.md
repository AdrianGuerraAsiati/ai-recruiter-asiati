# Employee Signed Documents — Design Specification

**Date:** 2026-10-02  
**Project:** Talent Intelligence / ai-recruiter-asiati  
**Status:** Approved design, pending implementation plan

## 1. Purpose

Add a private employee-document subsystem to Talent Intelligence so Talent can generate an initial employment document from an ASIATI corporate template, allow Human Resources to download an editable DOCX and a reference PDF, and archive the externally signed PDF as immutable evidence.

The first release covers:

- employment contracts;
- addenda / otrosíes;
- other signed employee documents.

The structure must remain extensible to additional document categories without replacing historical evidence.

## 2. Product decisions

The approved product behavior is:

1. Human Resources manages employee documents.
2. An employee can see and download only their own **current signed** documents.
3. Employees do not see drafts, pending-signature documents, replaced versions, voided records, internal notes, or other employees' documents.
4. Talent uses one fixed ASIATI corporate template for the initial contract in the MVP.
5. The source template currently exists as a text-selectable PDF.
6. That PDF will be reconstructed once into an internal DOCX template with dynamic fields.
7. Talent generates:
   - an editable DOCX;
   - a reference PDF.
8. Signing happens outside Talent for this release.
9. Human Resources uploads the externally signed PDF back into Talent.
10. Signed files are immutable. Corrections create a new version rather than replacing existing evidence.
11. The signed PDF is the authoritative archived artifact for this release.

## 3. Scope

### 3.1 In scope

- private employee document storage;
- fixed contract template;
- dynamic contract-data merge;
- DOCX generation;
- reference PDF generation;
- signed-PDF upload;
- SHA-256 integrity hash;
- immutable document versions;
- version history for HR;
- current-version selection;
- voiding without physical deletion;
- secure temporary downloads;
- employee self-service view for their current signed documents;
- HR administrative view;
- linkage to the existing employee and initial contract created during hiring;
- auditable actor/timestamp metadata.

### 3.2 Out of scope for this release

- native electronic signatures inside Talent;
- cryptographic signing certificates issued by Talent;
- DocuSign, Adobe Sign or other external e-signature integrations;
- automated legal-clause authoring by an LLM;
- OCR of contract templates;
- employee access to drafts or historical versions;
- storing employment documents in the candidate CV Knowledge Base;
- replacing Odoo as the HR master record;
- automatic deletion of historical signed files;
- a full contract-renewal lifecycle engine.

The legal wording comes only from the approved ASIATI corporate source template. Talent must not invent or alter legal clauses implicitly.

## 4. User roles and permissions

The subsystem introduces explicit document permissions rather than relying only on generic employee permissions.

Recommended permission catalog:

- `employee_documents.read_own`
- `employee_documents.read_all`
- `employee_documents.generate`
- `employee_documents.upload_signed`
- `employee_documents.manage`
- `employee_documents.download_history`

### Employee

Can:

- list their own current signed documents;
- download their own current signed PDF.

Cannot:

- generate;
- upload;
- void;
- inspect historical versions;
- inspect draft/reference files;
- access another employee's document by guessed ID.

### Admin / Human Resources

Can:

- generate documents;
- see document lifecycle state;
- upload signed PDFs;
- inspect version history;
- download generated files and signed historical versions;
- mark a document version as superseded through creation of a later version;
- void a document with audit metadata.

Authorization must be enforced server-side for every object lookup. Frontend hiding is not an authorization control.

## 5. Domain model

The existing Odoo contract sync is intentionally separate from the document subsystem.

### 5.1 EmployeeDocument

Represents the logical document across versions.

Suggested fields:

- `id` — UUID;
- `employee_id` — FK to `user_profiles.id`;
- `document_type` — `CONTRACT | ADDENDUM | OTHER`;
- `title`;
- `status` — `DRAFT | PENDING_SIGNATURE | SIGNED | VOID`;
- `contract_sync_id` — nullable relationship to the initial contract/outbox where applicable;
- `source_job_candidate_id` — nullable, for hiring traceability;
- `current_signed_version_id` — nullable FK;
- `created_by_sub`;
- `voided_by_sub` — nullable;
- `voided_at` — nullable;
- `void_reason` — nullable;
- `created_at`;
- `updated_at`.

A contract document can be linked to the structured contract data already captured during hiring, but its lifecycle is not controlled by Odoo delivery status.

### 5.2 EmployeeDocumentArtifact

Represents generated, non-authoritative output.

Suggested artifact kinds:

- `GENERATED_DOCX`;
- `REFERENCE_PDF`.

Fields:

- `id`;
- `document_id`;
- `artifact_kind`;
- `storage_key`;
- `mime_type`;
- `file_size`;
- `sha256`;
- `template_version`;
- `created_by_sub`;
- `created_at`.

Generated artifacts can be regenerated before signature if input data changes. They must not overwrite signed evidence.

### 5.3 EmployeeDocumentVersion

Represents one immutable signed-PDF evidence version.

Suggested fields:

- `id`;
- `document_id`;
- `version_number`;
- `storage_key`;
- `original_filename`;
- `mime_type`;
- `file_size`;
- `sha256`;
- `signed_at` — business date/time entered by HR when known;
- `uploaded_by_sub`;
- `uploaded_at`;
- `superseded_at` — nullable;
- `superseded_by_version_id` — nullable;
- `created_at`.

Constraints:

- unique `(document_id, version_number)`;
- signed artifacts cannot be updated after creation;
- current signed version is selected on the parent record;
- previous versions remain queryable by privileged HR users;
- no "replace file" operation exists.

## 6. State model

### DRAFT

Logical document exists but has not yet been prepared for signature.

### PENDING_SIGNATURE

DOCX/reference PDF have been generated and are ready for the external signature process.

### SIGNED

At least one signed PDF version exists and `current_signed_version_id` points to the active version.

### VOID

The logical document is no longer valid for operational use. Files and audit history remain preserved.

Transitions:

```text
DRAFT
  -> PENDING_SIGNATURE
  -> SIGNED

SIGNED
  -> SIGNED     (new immutable version supersedes the previous one)
  -> VOID

PENDING_SIGNATURE
  -> DRAFT      (regenerate before signing)
  -> VOID
```

No transition physically deletes signed evidence.

## 7. Template strategy

### 7.1 Source

ASIATI's existing text-selectable PDF is the legal/design source.

### 7.2 One-time reconstruction

The source PDF is manually reconstructed into a controlled DOCX template.

The template uses explicit placeholders such as:

- `{{ employee_full_name }}`
- `{{ employee_document_number }}`
- `{{ job_title }}`
- `{{ department }}`
- `{{ contract_type }}`
- `{{ contract_start_date }}`
- `{{ contract_end_date }}`
- `{{ monthly_wage }}`
- `{{ monthly_wage_words }}`

The final list of placeholders must be derived from the actual ASIATI PDF during implementation. Missing data must block generation rather than silently produce an incomplete legal document.

### 7.3 Template versioning

Even though the MVP exposes one fixed corporate template, the backend records a `template_version`.

This allows future template updates without making previously generated documents impossible to audit.

The application should not provide an end-user template editor in this release.

## 8. Generation flow

When HR generates the initial contract document:

1. Talent loads:
   - employee profile;
   - hiring/application context where available;
   - structured initial contract data;
   - fixed template version.
2. Talent validates required template variables.
3. Talent renders a DOCX.
4. Talent calculates SHA-256.
5. Talent stores it privately.
6. Talent converts the same rendered document to a reference PDF.
7. Talent calculates SHA-256 for the PDF.
8. Talent stores it privately.
9. Talent records both artifacts in PostgreSQL.
10. The document transitions to `PENDING_SIGNATURE`.
11. HR gets authenticated, short-lived download links.

The generated DOCX remains editable outside Talent. The reference PDF is for review/visual consistency only and is not treated as signed evidence.

## 9. Signed-document upload flow

HR selects the employee document and uploads the externally signed PDF.

Backend validation:

- PDF only for signed evidence in MVP;
- MIME and file signature validation, not filename extension alone;
- explicit size limit;
- non-empty file;
- authenticated HR permission;
- document belongs to target employee;
- document is not `VOID`.

On success:

1. Stream/read the file within the configured maximum.
2. Calculate SHA-256.
3. Allocate `version_number = previous + 1` transactionally.
4. Store to the private signed-document S3 prefix.
5. Insert immutable `EmployeeDocumentVersion`.
6. If a prior current version exists:
   - retain it;
   - set its supersession metadata.
7. Update `current_signed_version_id`.
8. Set logical document status to `SIGNED`.
9. Commit audit metadata.

If database persistence fails after S3 storage, cleanup/reconciliation must be handled so orphaned objects are detectable rather than silently lost.

## 10. Storage architecture

Employee documents must not use the current candidate/Bedrock prefix:

```text
documents/
```

That prefix is part of candidate CV indexing and is inappropriate for confidential employment records.

Recommended private namespace:

```text
employee-documents/
  employees/{employee_id}/
    documents/{document_id}/
      generated/
        {artifact_id}.docx
        {artifact_id}.pdf
      signed/
        v0001-{version_id}.pdf
        v0002-{version_id}.pdf
```

The application stores the S3 key, not a permanent public URL.

### S3 controls

- Block Public Access enabled;
- no public ACLs;
- encryption at rest;
- least-privilege ECS task access;
- download only through short-lived presigned GET URLs;
- uploads pass through authenticated backend validation for the MVP;
- generated/signed employee prefixes excluded from Bedrock Knowledge Base ingestion;
- lifecycle rules must not automatically destroy signed evidence without an explicit retention policy approved by ASIATI.

A separate bucket is preferable if operationally practical because it creates a clearer security and retention boundary. If the existing bucket is reused initially, the employee-document prefix must have explicit IAM isolation and must not be included in the CV data source.

## 11. Download model

The API never returns a permanent S3 URL.

For an authorized download:

1. API checks caller permission and employee ownership.
2. API resolves the exact artifact/version.
3. API creates a short-lived presigned GET URL.
4. Client uses the URL to download.
5. URL expires automatically.

Recommended TTL: a few minutes, configurable by environment.

For employees, the endpoint resolves only the current signed version. Historical IDs must still fail authorization even if guessed.

## 12. Integrity and immutability

Every stored artifact has a SHA-256 digest calculated by the backend.

For signed versions:

- the stored S3 key is unique and version-specific;
- database rows are append-only except for supersession metadata;
- no API supports overwriting the S3 object for an existing version;
- no normal UI supports physical deletion;
- a corrected file becomes a new version;
- HR can compare hash, upload date and actor in the audit view.

S3 Versioning can provide additional infrastructure protection, but application-level immutability must not depend solely on bucket versioning.

## 13. API surface

Exact route naming can follow current domain conventions, but the expected behavior is:

### HR routes

`GET /api/employees/{employee_id}/documents`

- lists all logical employee documents and HR-visible lifecycle metadata.

`POST /api/employees/{employee_id}/documents/contracts`

- creates/generates the initial contract document from structured hiring data.

`POST /api/employees/{employee_id}/documents`

- creates an ADDENDUM or OTHER logical document when appropriate.

`POST /api/employees/{employee_id}/documents/{document_id}/generate`

- generates/regenerates DOCX + reference PDF while not signed/void.

`POST /api/employees/{employee_id}/documents/{document_id}/signed-versions`

- multipart PDF upload;
- appends a new immutable signed version.

`POST /api/employees/{employee_id}/documents/{document_id}/void`

- voids logical document with mandatory reason.

`GET /api/employees/{employee_id}/documents/{document_id}/versions`

- HR-only historical signed versions.

`POST /api/employees/{employee_id}/documents/{document_id}/downloads/{artifact_or_version_id}`

- authorization + short-lived download URL.

### Employee self-service routes

`GET /api/me/documents`

- only current signed, non-void documents owned by the authenticated employee.

`POST /api/me/documents/{document_id}/download`

- only current signed PDF for that employee.

The backend derives the employee identity from the authenticated principal rather than accepting an arbitrary employee ID for self-service.

## 14. User interface

### 14.1 HR employee profile

Add a **Documentos** section to the employee administration experience.

Summary per document:

- type;
- title;
- state;
- current signed version;
- date generated;
- signed upload date;
- actions permitted by state.

Key actions:

- `Generar contrato`;
- `Descargar DOCX`;
- `Descargar PDF de referencia`;
- `Subir PDF firmado`;
- `Ver historial`;
- `Anular`.

When uploading another signed PDF, UI must explicitly communicate that a new immutable version will be created and the current signed version will be superseded.

### 14.2 Employee portal

Add **Mis documentos**.

The employee sees only:

- document title/type;
- signed/current state;
- relevant effective/signature date;
- `Descargar PDF`.

Do not expose:

- salary metadata separately unless it is part of the document itself;
- generated DOCX;
- reference PDF;
- prior versions;
- uploader identity;
- internal contract sync status;
- HR notes.

## 15. Relationship with hiring

The current hiring flow already creates:

- employee;
- Talent login;
- onboarding;
- Odoo employee sync;
- structured initial contract sync.

Document generation should be **available immediately after successful Talent hiring** when required contract data exists.

The hiring transaction must not fail because DOCX/PDF generation fails.

Recommended boundary:

```text
Hire candidate
    |
    +--> Employee created          [required]
    +--> Talent credentials        [required]
    +--> Onboarding                [required/isolated existing behavior]
    +--> Odoo employee outbox      [durable]
    +--> Odoo contract outbox      [durable]
    +--> Contract document record  [prepared / recoverable]
             |
             +--> Generate DOCX/PDF on explicit HR action
```

The document workflow is therefore recoverable and does not make employment creation dependent on document conversion infrastructure.

## 16. Relationship with Odoo

Odoo and Talent serve different concerns:

- structured contract data may synchronize to `hr.contract`;
- signed file evidence is managed in Talent for this release.

No binary signed PDF is pushed to Odoo in the MVP.

Future Odoo attachment synchronization can be added as a separate outbox process if ASIATI later requires signed documents in Odoo as well.

An Odoo failure must not affect the integrity of the Talent document archive.

## 17. Addenda / otrosíes

The subsystem is intentionally many-documents-per-employee.

An addendum:

- is a new `EmployeeDocument` with type `ADDENDUM`;
- can reference a prior contract/document through future optional relationship metadata;
- has its own generated artifacts;
- has its own signed version history;
- never mutates the original signed contract.

The initial MVP can permit HR to create an addendum record and upload/generate its document while more advanced contract-history semantics remain separate.

## 18. Other signed documents

`OTHER` supports documents such as acknowledgements, policies or authorizations without introducing a new database table for each category.

MVP metadata should include a human-readable title. More specific categories can be introduced later if reporting requirements justify them.

## 19. Error handling

Examples:

### Generation validation failure

Return 422 with a safe list of missing required business fields. Do not generate a partially populated legal document.

### Template or converter failure

Return 502/503 as appropriate and keep the logical document recoverable. Do not mark it `PENDING_SIGNATURE` until both expected generated artifacts are durable.

### Invalid signed upload

Return 422 for non-PDF, malformed PDF, empty file, or invalid metadata.

### S3 failure

Do not create a database version that references a nonexistent object.

### Concurrent uploads

Version number allocation and current-version update must be transactional/locked to avoid two uploads both becoming the same version.

### Authorization failure

Use 403/404 according to current application security conventions without leaking another employee's document metadata.

## 20. Audit requirements

For sensitive actions, preserve:

- authenticated actor;
- employee;
- document;
- version/artifact;
- action;
- timestamp;
- SHA-256;
- filename where applicable;
- void reason where applicable.

At minimum, the document/version tables provide durable actor/timestamp history. If the project already has or later adds a centralized audit-event subsystem, these operations should also emit audit events.

## 21. Security and privacy

Employment contracts can include financial and identity data.

Controls required:

- strict RBAC;
- owner checks for employee self-service;
- private S3;
- short-lived signed URLs;
- encryption at rest and TLS in transit;
- no indexing into Bedrock;
- no document contents written to application logs;
- no signed URL values in normal logs;
- sanitized errors;
- MIME/file-signature verification;
- explicit upload size limits;
- unique non-user-controlled storage keys;
- no direct use of original filenames as S3 paths;
- retention/deletion policy handled deliberately rather than by generic candidate-document lifecycle rules.

## 22. Deployment/configuration

Expected environment configuration:

- employee-document bucket or bucket name;
- private prefix;
- template identifier/path/version;
- max upload bytes;
- presigned URL TTL;
- AWS region (`us-east-2` for this project).

IAM for the application runtime should be limited to the configured employee-document namespace and required S3 actions.

Infrastructure deployment must confirm that the Bedrock candidate data source does not include the employee-document location.

## 23. Testing strategy

### Backend unit/domain tests

- create logical contract document;
- required contract fields validated;
- signed version numbers increment;
- prior signed version remains intact;
- current version changes atomically;
- SHA-256 stored;
- void retains files/history;
- employee can only resolve own current signed document;
- HR can inspect history;
- guessed foreign employee document is denied.

### Storage tests

- generated keys never use `documents/`;
- signed version keys are unique;
- presigned URLs are generated only after authorization;
- upload rejects non-PDF/malformed/oversized files.

### API tests

- generation;
- upload;
- second signed version;
- version history;
- self-service listing;
- self-service download;
- void;
- permission matrix.

### Frontend tests

- HR document section lifecycle actions;
- upload confirmation explains immutable versioning;
- employee portal only shows current signed documents;
- employee cannot see historical/generated artifacts.

### Migration tests

- new tables/constraints/indexes;
- migration chain continues after revision `038`;
- PostgreSQL smoke migration succeeds.

## 24. Migration compatibility

This subsystem should introduce new tables rather than expanding `odoo_contract_syncs` into a document store.

The existing `odoo_contract_syncs` table remains the integration state for the initial structured Odoo contract.

Employee document history remains independent so future renewals, addenda and evidence do not overwrite the existing one-contract-per-employee Odoo MVP assumptions.

## 25. Acceptance criteria

The MVP is complete when:

1. HR can generate an initial employee contract from the fixed ASIATI template.
2. HR can download both DOCX and reference PDF.
3. HR can upload a signed PDF.
4. The signed PDF produces an immutable version with SHA-256.
5. Uploading a corrected signed PDF creates version 2 and preserves version 1.
6. HR can see both versions and identify the current one.
7. An employee can see and download only their own current signed version.
8. An employee cannot access drafts, generated artifacts, history, or another employee's documents.
9. Files are private in S3 and downloads use expiring URLs.
10. Employee documents are not included in the Bedrock CV Knowledge Base.
11. Odoo outages do not block document archival.
12. No existing candidate/hiring/onboarding behavior regresses.

## 26. Future extensions

Not part of the MVP, but this design intentionally leaves room for:

- native electronic signature workflows;
- signature-provider integrations;
- contract renewal history;
- termination documents;
- approved template administration;
- multiple country/legal-entity templates;
- Odoo attachment synchronization;
- document expiry/reminder workflows;
- employee acknowledgement workflows;
- organization-wide retention policies;
- stronger S3 immutability controls such as Object Lock where operational/legal requirements justify it.
