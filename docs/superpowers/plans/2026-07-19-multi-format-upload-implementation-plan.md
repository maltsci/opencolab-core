# Multi-Format Research Asset Upload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Use superpowers:test-driven-development before writing each production change.

**Goal:** Expand material intake from PDF and ZIP to safe direct files, compound archives, external URL/DOI references, generated documents, and scientific formats while preserving one stable asset identity and immutable revisions.

**Architecture:** A shared intake validates extension, signature, size, archive structure, member manifest, and governance context before sealing a candidate AssetRevision. Direct files create one primary member; ZIP creates one package member plus extracted members in the same revision and fails atomically on any unsafe member. A parser registry emits normalized text blocks for parseable members, while catalog-only scientific members remain discoverable without entering text indexing.

**Tech Stack:** FastAPI multipart upload, stdlib ZIP and CSV/JSON parsing, python-docx, python-pptx, openpyxl, existing PDF parser, LangChain documents/chunks, Qdrant, React/TypeScript, pytest.

---

## Supported Formats

Use these exact groups:

```python
PARSEABLE_EXTENSIONS = frozenset(
    {
        ".pdf",
        ".docx",
        ".pptx",
        ".txt",
        ".md",
        ".csv",
        ".tsv",
        ".xlsx",
        ".json",
        ".jsonl",
    }
)

CATALOG_ONLY_EXTENSIONS = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".tif",
        ".tiff",
        ".wav",
        ".mp3",
        ".flac",
        ".fasta",
        ".fa",
        ".fastq",
        ".fq",
        ".vcf",
        ".bam",
        ".bai",
        ".sam",
        ".cram",
        ".crai",
        ".bcf",
        ".bed",
        ".gff",
        ".gtf",
        ".seq",
        ".ab1",
    }
)

ARCHIVE_EXTENSIONS = frozenset({".zip"})
COMPOUND_SUFFIXES = frozenset(
    {
        ".fastq.gz",
        ".fq.gz",
        ".fasta.gz",
        ".fa.gz",
        ".vcf.gz",
        ".bed.gz",
        ".gff.gz",
        ".gtf.gz",
    }
)
```

Reject `.doc`, `.xls`, `.ppt`, macro-enabled Office formats, executables, scripts, disk images, nested archives, encrypted archives, unknown formats, and a gzip suffix that is not in `COMPOUND_SUFFIXES`.

## Task 1: Add File-Type Policy and Signature Validation

**Files:**

- Create: `backend/app/services/file_type_policy.py`
- Modify: `backend/app/core/config.py`
- Modify: `.env.template`
- Test: `tests/test_file_type_policy.py`

- [ ] **Step 1: Write failing policy tests**

Test:

- Every supported extension maps to `parseable`, `catalog_only`, or `archive`.
- Case-insensitive extensions normalize.
- A renamed executable with `.pdf` is rejected.
- PDF, ZIP/OOXML, PNG, JPEG, TIFF, WAV, MP3, FLAC, BAM/BAI, CRAM/CRAI, AB1, and gzip signatures are identified conservatively.
- DOCX, PPTX, and XLSX ZIP containers are distinguished by required internal entries.
- Macro-enabled Office content is rejected.
- Plain-text formats reject NUL-heavy or binary content.
- FASTA, FASTQ, and VCF receive conservative text-shape validation.

- [ ] **Step 2: Run and confirm failure**

```bash
backend/.venv/bin/python -m pytest tests/test_file_type_policy.py -q
```

Expected: FAIL because the policy module is absent.

- [ ] **Step 3: Add upload limits**

Add settings with environment aliases:

```python
upload_max_file_size_mb: int = Field(
    default=500, validation_alias="OPENCOLAB_UPLOAD_MAX_FILE_SIZE_MB"
)
upload_max_archive_entries: int = Field(
    default=100, validation_alias="OPENCOLAB_UPLOAD_MAX_ARCHIVE_ENTRIES"
)
upload_max_archive_expanded_mb: int = Field(
    default=500, validation_alias="OPENCOLAB_UPLOAD_MAX_ARCHIVE_EXPANDED_MB"
)
upload_max_archive_ratio: int = Field(
    default=100, validation_alias="OPENCOLAB_UPLOAD_MAX_ARCHIVE_RATIO"
)
upload_max_table_rows: int = Field(
    default=100_000, validation_alias="OPENCOLAB_UPLOAD_MAX_TABLE_ROWS"
)
upload_max_table_cells: int = Field(
    default=1_000_000, validation_alias="OPENCOLAB_UPLOAD_MAX_TABLE_CELLS"
)
upload_max_json_depth: int = Field(
    default=32, validation_alias="OPENCOLAB_UPLOAD_MAX_JSON_DEPTH"
)
```

Document each setting in `.env.template`.

- [ ] **Step 4: Implement the classification result**

```python
@dataclass(frozen=True)
class FileTypeDecision:
    extension: str
    media_type: str
    processing_mode: Literal["parseable", "catalog_only", "archive"]
    detected_format: str


class UnsupportedFileTypeError(ValueError):
    pass
```

Required public signature: `def validate_file_type(*, filename: str, declared_media_type: str | None, header: bytes, complete_content: bytes | None = None) -> FileTypeDecision`.

Use stdlib signature checks and safe ZIP entry inspection. Do not trust browser `Content-Type`. Do not fully decompress ordinary archives in this function.

- [ ] **Step 5: Run and commit**

```bash
backend/.venv/bin/python -m pytest tests/test_file_type_policy.py -q
git add backend/app/services/file_type_policy.py backend/app/core/config.py .env.template tests/test_file_type_policy.py
git commit -m "feat: validate research upload formats"
```

## Task 2: Add Parser Dependencies and Registry

**Files:**

- Modify: `backend/requirements.txt`
- Modify: `backend/requirements-api.txt`
- Modify: `backend/requirements-worker.txt`
- Create: `backend/app/services/parsers/__init__.py`
- Create: `backend/app/services/parsers/base.py`
- Create: `backend/app/services/parsers/registry.py`
- Test: `tests/test_parser_registry.py`

- [ ] **Step 1: Write failing registry tests**

Assert:

- Every parseable extension has one parser.
- Catalog-only and ZIP extensions have no text parser.
- Unknown extensions raise `UnsupportedParserError`.
- Parser results always contain bounded normalized blocks and metadata.

- [ ] **Step 2: Run and confirm failure**

```bash
backend/.venv/bin/python -m pytest tests/test_parser_registry.py -q
```

- [ ] **Step 3: Add bounded dependencies**

Add the same direct dependencies to the requirement variants used by the API and worker:

```text
python-docx>=1.1,<2
python-pptx>=1.0,<2
openpyxl>=3.1,<4
```

Do not add OCR, audio transcription, pandas, or a system-level MIME dependency in V1.

- [ ] **Step 4: Define the parser contract**

```python
@dataclass(frozen=True)
class ParsedBlock:
    text: str
    metadata: Mapping[str, str | int | float | bool]


@dataclass(frozen=True)
class ParseResult:
    blocks: tuple[ParsedBlock, ...]
    document_metadata: Mapping[str, str | int | float | bool]


class ResearchFileParser(Protocol):
    parse: Callable[..., ParseResult]
```

The concrete parser method has the exact contract `parse(*, content: bytes, filename: str, limits: ParserLimits) -> ParseResult`. `ParserLimits` contains maximum bytes, rows, cells, JSON depth, and maximum normalized text characters. The registry accepts a validated `FileTypeDecision`, not an untrusted filename.

- [ ] **Step 5: Run and commit**

```bash
backend/.venv/bin/python -m pytest tests/test_parser_registry.py -q
git add backend/requirements.txt backend/requirements-api.txt backend/requirements-worker.txt backend/app/services/parsers tests/test_parser_registry.py
git commit -m "feat: add research file parser registry"
```

## Task 3: Implement Plain Text and Structured Data Parsers

**Files:**

- Create: `backend/app/services/parsers/text_parser.py`
- Create: `backend/app/services/parsers/delimited_parser.py`
- Create: `backend/app/services/parsers/json_parser.py`
- Modify: `backend/app/services/parsers/registry.py`
- Test: `tests/test_structured_file_parsers.py`

- [ ] **Step 1: Write failing parser tests**

Fixtures must cover:

- UTF-8, UTF-8 BOM, and valid UTF-16 text.
- Invalid undecodable text.
- Markdown preserved as text without executing HTML.
- CSV and TSV quoted values, large fields, row/cell limits, and spreadsheet formula text.
- JSON object, array, scalar, excessive nesting, and non-finite values.
- JSONL valid rows and a malformed row with its line number.
- Empty files.

- [ ] **Step 2: Run and confirm failure**

```bash
backend/.venv/bin/python -m pytest tests/test_structured_file_parsers.py -q
```

- [ ] **Step 3: Implement safe normalization**

Text parser:

- Detect BOM.
- Otherwise decode UTF-8 strictly.
- Normalize line endings to `\n`.
- Remove no content except NUL, which causes rejection.
- Split into blocks at bounded paragraph boundaries.

Delimited parser:

- Use `csv.reader`, not manual splitting.
- Set a bounded `csv.field_size_limit`.
- Preserve formulas as literal strings; never evaluate them.
- Emit one normalized row block with column headers in metadata.

JSON parser:

- Use `json.loads` with `parse_constant` that rejects non-finite values.
- Measure depth before flattening.
- Emit deterministic JSON Pointer paths.
- For JSONL, parse one line at a time.

- [ ] **Step 4: Run and commit**

```bash
backend/.venv/bin/python -m pytest tests/test_structured_file_parsers.py -q
git add backend/app/services/parsers/text_parser.py backend/app/services/parsers/delimited_parser.py backend/app/services/parsers/json_parser.py backend/app/services/parsers/registry.py tests/test_structured_file_parsers.py
git commit -m "feat: parse text and structured research files"
```

## Task 4: Implement DOCX, PPTX, and XLSX Parsers

**Files:**

- Create: `backend/app/services/parsers/docx_parser.py`
- Create: `backend/app/services/parsers/pptx_parser.py`
- Create: `backend/app/services/parsers/xlsx_parser.py`
- Modify: `backend/app/services/parsers/registry.py`
- Test: `tests/test_office_file_parsers.py`
- Create: `tests/fixtures/uploads/README.md`

- [ ] **Step 1: Add minimal generated fixtures and failing tests**

The fixture README documents how test files were generated and confirms they contain no confidential data.

Test:

- DOCX paragraphs and tables retain document order.
- PPTX slide text and speaker notes are extracted per slide.
- XLSX reads formula source text with `data_only=False`; formulas are never executed.
- Hidden spreadsheet sheets are included but marked `hidden=true`.
- Row and cell limits stop oversized workbooks.
- External relationships and macros are rejected by file-type validation.
- Embedded executable objects and unsafe XML entity declarations are rejected before library parsing.
- Embedded images are not OCR processed.

- [ ] **Step 2: Run and confirm failure**

```bash
backend/.venv/bin/python -m pytest tests/test_office_file_parsers.py -q
```

- [ ] **Step 3: Implement parsers**

Use:

```python
Document(BytesIO(content))
Presentation(BytesIO(content))
load_workbook(BytesIO(content), read_only=True, data_only=False)
```

Close workbooks in `finally`. Parser metadata must contain document position only: paragraph index, table index, slide number, sheet name, and row number. Do not copy Office author/company/custom properties into public catalog metadata.

- [ ] **Step 4: Run and commit**

```bash
backend/.venv/bin/python -m pytest tests/test_office_file_parsers.py -q
git add backend/app/services/parsers/docx_parser.py backend/app/services/parsers/pptx_parser.py backend/app/services/parsers/xlsx_parser.py backend/app/services/parsers/registry.py tests/test_office_file_parsers.py tests/fixtures/uploads/README.md
git commit -m "feat: parse office research files"
```

## Task 5: Adapt PDF Parsing to the Registry

**Files:**

- Create: `backend/app/services/parsers/pdf_parser.py`
- Modify: `backend/app/services/parsers/registry.py`
- Modify: `backend/app/services/pdf_parser.py`
- Test: `tests/test_pdf_parser_registry.py`

- [ ] **Step 1: Write a failing compatibility test**

Assert the registry adapter produces the same normalized text and page metadata as the current PDF path for the existing PDF fixture.

- [ ] **Step 2: Run and confirm failure**

```bash
backend/.venv/bin/python -m pytest tests/test_pdf_parser_registry.py -q
```

- [ ] **Step 3: Add a thin adapter**

The new parser calls the existing PDF service and maps pages to `ParsedBlock`. Do not duplicate marker integration. Keep the old module as the low-level PDF implementation until all callers use the registry.

- [ ] **Step 4: Run and commit**

```bash
backend/.venv/bin/python -m pytest tests/test_pdf_parser_registry.py tests/test_source_extractions.py -q
git add backend/app/services/parsers/pdf_parser.py backend/app/services/parsers/registry.py backend/app/services/pdf_parser.py tests/test_pdf_parser_registry.py
git commit -m "refactor: route pdf parsing through registry"
```

## Task 6: Generalize ZIP Intake and Harden Archive Security

**Files:**

- Modify: `backend/app/services/zip_service.py`
- Test: `tests/test_zip_service.py`

- [ ] **Step 1: Write failing ZIP security tests**

Cover:

- Mixed allowlisted parseable and catalog-only files.
- Directory entries ignored.
- Nested ZIP rejected.
- Unsupported file rejected with entry name only.
- Path traversal with `/`, `..`, backslash, drive prefix, or absolute path rejected.
- Symlink entries rejected from Unix mode bits.
- Encrypted entries rejected.
- Duplicate normalized names rejected.
- Entry count, individual size, total expanded size, and compression ratio enforced.
- CRC failure produces a generic archive error.
- macOS metadata such as `__MACOSX/` and `.DS_Store` is ignored.
- The original ZIP is retained as a package member and every safe file is represented as an extracted member in the same revision.
- Any unsupported, unsafe, malformed, encrypted, or unknown ordinary member rejects the whole candidate revision.
- Directory names remain normalized member paths; ZIP intake does not create Collections or child ResearchAssets.

- [ ] **Step 2: Run and confirm failure**

```bash
backend/.venv/bin/python -m pytest tests/test_zip_service.py -q
```

- [ ] **Step 3: Replace PDF-only output**

Use:

```python
@dataclass(frozen=True)
class ArchiveMemberCandidate:
    filename: str
    normalized_path: str
    content: bytes
    decision: FileTypeDecision
    sha256: str
```

Required public signature: `def inspect_zip_revision(content: bytes, *, limits: ArchiveLimits) -> tuple[ArchiveMemberCandidate, ...]`.

Validate every entry through `validate_file_type`. Read entries in bounded chunks while measuring actual expanded bytes. Never extract to the filesystem. Raise one sanitized archive error for any unsafe archive-level or member-level condition. Return candidates only after the entire archive validates, so callers cannot persist a partial revision.

- [ ] **Step 4: Run and commit**

```bash
backend/.venv/bin/python -m pytest tests/test_zip_service.py -q
git add backend/app/services/zip_service.py tests/test_zip_service.py
git commit -m "feat: harden multi-format zip uploads"
```

## Task 7: Create a Shared Governed Upload Intake

**Files:**

- Create: `backend/app/services/research_upload_service.py`
- Modify: `backend/app/api/sources.py`
- Modify: `backend/app/services/research_asset_service.py`
- Modify: `backend/app/services/file_storage.py`
- Test: `tests/test_research_upload_service.py`

- [ ] **Step 1: Write failing intake tests**

Test direct and ZIP uploads:

- Validation happens before permanent persistence.
- A direct file creates one ResearchAsset, one candidate revision, and one primary member.
- A ZIP creates one ResearchAsset, one candidate revision, one package member, and one extracted member per safe entry.
- Governance defaults match personal/project/session/library context.
- Parseable assets start `processing`.
- Catalog-only assets start `catalog_only`.
- Any direct-file or ZIP-member failure leaves no current revision, permanent storage, Source, or member rows from that candidate.
- Duplicate content can coexist with a distinct catalog identity if existing product behavior allows it.
- Client errors never include local storage paths or parser exception text.

- [ ] **Step 2: Run and confirm failure**

```bash
backend/.venv/bin/python -m pytest tests/test_research_upload_service.py -q
```

- [ ] **Step 3: Implement one intake contract**

```python
@dataclass(frozen=True)
class UploadContext:
    user_id: UUID
    scope: Literal["personal", "project", "session", "library"]
    owning_group_id: UUID
    project_id: UUID | None
    session_id: UUID | None


@dataclass(frozen=True)
class UploadedResearchAsset:
    research_asset_id: UUID
    asset_revision_id: UUID
    member_ids: tuple[UUID, ...]
    processing_state: AssetRevisionState
```

Required public signature: `async def ingest_research_upload(db: AsyncSession, *, filename: str, content: bytes, context: UploadContext) -> UploadedResearchAsset`.

The service:

1. Validates the outer file.
2. Inspects the complete ZIP atomically when needed.
3. Creates temporary storage for the original direct file or ZIP package and all extracted safe members.
4. Creates one ResearchAsset, one AssetRevision, its AssetContentMembers and Sources, optional scientific DataAsset metadata, and baseline access state in one transaction.
5. Finalizes all storage only after database flush succeeds.
6. Enqueues parseable members under one revision-processing job and preserves catalog-only members in the manifest.
7. Seals and makes the revision current only after all required members reach their terminal valid state.
8. Cleans all candidate storage and rows on validation failure; a processing failure retains a non-current failed revision with sanitized diagnostics.

- [ ] **Step 4: Run and commit**

```bash
backend/.venv/bin/python -m pytest tests/test_research_upload_service.py tests/test_research_asset_governance.py -q
git add backend/app/services/research_upload_service.py backend/app/api/sources.py backend/app/services/research_asset_service.py backend/app/services/file_storage.py tests/test_research_upload_service.py
git commit -m "feat: ingest governed research uploads"
```

## Task 8: Route Worker Processing Through the Parser Registry

**Files:**

- Modify: `backend/app/worker/main.py`
- Modify: `backend/app/models/source.py`
- Modify: `backend/app/schemas/source.py`
- Create: `backend/alembic/versions/l2f3g4h5i6j7_add_source_file_format.py`
- Test: `tests/test_worker_multi_format.py`
- Modify: `tests/test_worker_startup.py`

- [ ] **Step 1: Write failing worker tests**

Assert:

- Every parseable member reaches normalized extraction and chunk persistence.
- Catalog-only sources never call parser, embedding, or Qdrant.
- One required member parser failure produces a failed, non-current revision with a safe code.
- Retrying a failed revision is idempotent.
- Successful processing seals the revision exactly once and does not write directly to Qdrant.

- [ ] **Step 2: Run and confirm failure**

```bash
backend/.venv/bin/python -m pytest tests/test_worker_multi_format.py tests/test_worker_startup.py -q
```

- [ ] **Step 3: Add processing states**

Expose these stable revision states:

```text
pending
processing
ready
failed
```

Internal member progress may retain finer-grained log stages. A revision may be ready when its parseable members completed and its catalog-only members were intentionally skipped; do not describe catalog-only content as parsed.

Add `detected_format` and `processing_mode` to `Source`. Persist the validated values from intake; the worker must not redetect from an extension.

Create the migration with:

```python
revision = "l2f3g4h5i6j7"
down_revision = "k1e2f3g4h5i6"
```

Add nullable columns first, backfill existing sources as `detected_format="pdf"` and `processing_mode="parseable"`, then make them non-null where supported. Existing PDF sources keep their current processing state.

- [ ] **Step 4: Update worker flow**

The worker loads the revision manifest and validated format for each member, invokes the registry, and persists normalized extraction/chunks with `research_asset_id`, `asset_revision_id`, and `asset_content_member_id`. It skips catalog-only members and emits structured logs containing identifiers and detected format only.

After every required member succeeds or is intentionally catalog-only, call `seal_revision` exactly once. Phase 4 will add the transactional `revision_ready` event and owns embedding and Qdrant writes; this worker must not encode user, grant, project, classification, or other authorization state into chunks.

- [ ] **Step 5: Run and commit**

```bash
backend/.venv/bin/python -m pytest tests/test_worker_multi_format.py tests/test_worker_startup.py tests/test_rag_service.py -q
git add backend/app/worker/main.py backend/app/models/source.py backend/app/schemas/source.py backend/alembic/versions/l2f3g4h5i6j7_add_source_file_format.py tests/test_worker_multi_format.py tests/test_worker_startup.py
git commit -m "feat: process multi-format research assets"
```

## Task 9: Register External References and Explicit Local Snapshots

**Files:**

- Create: `backend/app/services/external_reference_service.py`
- Create: `backend/app/api/external_references.py`
- Modify: `backend/app/main.py`
- Test: `tests/test_external_reference_service.py`
- Test: `tests/test_external_reference_api.py`

- [ ] **Step 1: Write failing service and API tests**

Cover:

- Registering a URL or DOI creates an `external_reference` ResearchAsset, revision 1, and one external member containing encrypted reference data and safe public metadata.
- Registration never fetches the remote body and works in an air-gapped deployment.
- Credentials, URL user-info, authorization headers, and unapproved query secrets are rejected.
- An explicit snapshot action fetches through the deployment's allowlisted outbound adapter, validates redirect targets and size, and creates a new immutable managed revision.
- A failed or denied snapshot leaves the external revision current and returns a sanitized error.
- Snapshot authorization requires `asset:manage`; snapshot content receives normal classification and revision authorization.

- [ ] **Step 2: Run and confirm failure**

```bash
backend/.venv/bin/python -m pytest tests/test_external_reference_service.py tests/test_external_reference_api.py -q
```

Expected: FAIL because the service and routes do not exist.

- [ ] **Step 3: Implement metadata-only registration and snapshot**

Required public contracts:

```python
async def register_external_reference(
    db: AsyncSession,
    *,
    actor: User,
    reference_type: Literal["url", "doi"],
    reference: str,
    metadata: ExternalReferenceMetadata,
    governance: GovernanceCreationContext,
) -> ResearchAsset

async def snapshot_external_reference(
    db: AsyncSession,
    *,
    actor: User,
    asset_id: UUID,
    revision_id: UUID,
) -> AssetRevision
```

Registration stores only encrypted reference identity and caller-supplied safe metadata. Snapshotting is a separate, explicit command: it resolves server-side, applies scheme/host/private-network protections, validates the downloaded type with the same intake policy, and delegates to the revision intake path. Do not add a background crawler.

Expose:

```text
POST /api/v1/research-assets/external-references
POST /api/v1/research-assets/{asset_id}/revisions/{revision_id}/snapshot
```

- [ ] **Step 4: Run and commit**

```bash
backend/.venv/bin/python -m pytest tests/test_external_reference_service.py tests/test_external_reference_api.py -q
git add backend/app/services/external_reference_service.py backend/app/api/external_references.py backend/app/main.py tests/test_external_reference_service.py tests/test_external_reference_api.py
git commit -m "feat: add governed external references"
```

## Task 10: Update Frontend Upload and Generic Asset Preview

**Files:**

- Modify: `frontend/src/hooks/use-file-drop.ts`
- Modify: `frontend/src/pages/Library.tsx`
- Modify: `frontend/src/pages/ProjectAssets.tsx`
- Modify: `frontend/src/components/library/AssetDetailDrawer.tsx`
- Modify: `frontend/src/types/research-asset.ts`
- Modify: `frontend/src/locales/en-US.json`
- Modify: `frontend/src/locales/zh-CN.json`

- [ ] **Step 1: Add frontend type checks first**

Update source and asset types with:

```typescript
export type ProcessingMode = 'parseable' | 'catalog_only'

export type RevisionProcessingState =
  | 'pending'
  | 'processing'
  | 'ready'
  | 'failed'
```

Run:

```bash
cd frontend && npm run build
```

Expected: FAIL at exhaustive state handling and old file accept assumptions.

- [ ] **Step 2: Update accepted file list**

Export one accepted-extension constant from `use-file-drop.ts` and reuse it for drag/drop validation and Ant Design `Upload.accept`. Do not maintain separate lists in the two pages.

Display:

- parseable formats under “Searchable content”;
- catalog-only formats under “Catalog metadata only”;
- ZIP atomic-validation limitations and “one asset with multiple members” behavior in help text;
- a generic localized rejection message with the rejected filename.

- [ ] **Step 3: Generalize detail rendering**

`AssetDetailDrawer`:

- keeps PDF preview when content preview is authorized;
- renders extracted text preview for other parseable formats;
- renders safe catalog metadata and “Content processing is not supported” for catalog-only formats;
- renders the current revision number and safe member manifest without exposing Source or storage identities;
- never constructs a content URL when the user lacks the relevant capability.

All strings must use new i18n keys in both locale files.

- [ ] **Step 4: Build and commit**

```bash
cd frontend && npm run build
git add frontend/src/hooks/use-file-drop.ts frontend/src/pages/Library.tsx frontend/src/pages/ProjectAssets.tsx frontend/src/components/library/AssetDetailDrawer.tsx frontend/src/types/research-asset.ts frontend/src/locales/en-US.json frontend/src/locales/zh-CN.json
git commit -m "feat: support multi-format research uploads"
```

Expected: build succeeds.

## Task 11: Phase Verification

- [ ] **Step 1: Run security and parser suites**

```bash
backend/.venv/bin/python -m pytest tests/test_file_type_policy.py tests/test_parser_registry.py tests/test_structured_file_parsers.py tests/test_office_file_parsers.py tests/test_zip_service.py tests/test_research_upload_service.py tests/test_worker_multi_format.py -q
```

Expected: PASS.

- [ ] **Step 2: Run full checks**

```bash
backend/.venv/bin/python -m pytest -q
cd frontend && npm run build
git diff --check
pre-commit run
```

Expected: PASS.

- [ ] **Step 3: Manual smoke test**

Upload one file from each parseable family, one catalog-only BAM/BAI pair, and one mixed ZIP. Confirm:

- only public metadata is visible in catalog responses;
- parsed files reach ready;
- BAM/BAI remain catalog-only members;
- the ZIP has one ResearchAsset and one revision with package and extracted members;
- one invalid ZIP member rejects the complete candidate revision and leaves no permanent storage or current revision.

- [ ] **Step 4: Create a checkpoint commit only if verification changed files**

```bash
git add backend frontend tests .env.template
git commit -m "test: verify multi-format research uploads"
```

Do not create an empty commit.
