# Governance Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Use superpowers:test-driven-development before writing each production change.

**Goal:** Add multi-research-group ownership, universal ResearchAsset governance, immutable asset revisions and content members, DataAsset specialization, policy records, and a deterministic migration that preserves existing legitimate readers without retaining legacy authorization bypasses.

**Architecture:** Keep `ResearchAsset` as the stable catalog and governance envelope for every material. Store actual managed files, external references, generated content, and archive members under immutable `AssetRevision` and `AssetContentMember` rows. Add normalized research-group membership and project ownership, keep `DataAsset` as scientific metadata only, and evaluate revision-aware capabilities through one policy service.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic V2, Alembic, PostgreSQL, SQLite test database, pytest.

---

## Task 1: Define Stable Governance Types

**Files:**

- Create: `backend/app/core/governance.py`
- Test: `tests/test_governance_types.py`

- [ ] **Step 1: Write the failing type tests**

```python
from app.core.governance import (
    AssetCategory,
    AssetClassification,
    AssetContentMode,
    AssetLifecycleStatus,
    AssetMemberRole,
    AssetRevisionState,
    Capability,
    GovernanceReviewStatus,
)


def test_governance_values_are_stable_api_strings() -> None:
    assert AssetClassification.PUBLIC == "public"
    assert AssetClassification.INTERNAL == "internal"
    assert AssetClassification.CONFIDENTIAL == "confidential"
    assert AssetClassification.RESTRICTED == "restricted"
    assert AssetClassification.TOP_SECRET == "top_secret"
    assert Capability.METADATA_VIEW == "metadata:view"
    assert Capability.CONTENT_USE_IN_AGENT == "content:use_in_agent"
    assert AssetLifecycleStatus.ACTIVE == "active"
    assert GovernanceReviewStatus.PENDING == "pending"
    assert AssetCategory.SCIENTIFIC_DATA == "scientific_data"
    assert AssetRevisionState.READY == "ready"
    assert AssetMemberRole.PRIMARY == "primary"
    assert AssetContentMode.MANAGED == "managed"
```

- [ ] **Step 2: Run the focused test and confirm failure**

Run:

```bash
backend/.venv/bin/python -m pytest tests/test_governance_types.py -q
```

Expected: FAIL because `app.core.governance` does not exist.

- [ ] **Step 3: Add the governance types**

```python
from enum import StrEnum


class AssetClassification(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"
    TOP_SECRET = "top_secret"


class Capability(StrEnum):
    METADATA_VIEW = "metadata:view"
    CONTENT_PREVIEW = "content:preview"
    CONTENT_DOWNLOAD = "content:download"
    CONTENT_USE_IN_AGENT = "content:use_in_agent"
    ASSET_MANAGE = "asset:manage"


class AssetLifecycleStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class CatalogStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    WITHDRAWN = "withdrawn"


class GovernanceReviewStatus(StrEnum):
    PENDING = "pending"
    REVIEWED = "reviewed"


class AssetCategory(StrEnum):
    UPLOADED_MATERIAL = "uploaded_material"
    EXTERNAL_REFERENCE = "external_reference"
    GENERATED_DOCUMENT = "generated_document"
    RESEARCH_MEMORY = "research_memory"
    CONVERSATION_ARTIFACT = "conversation_artifact"
    EXPERIMENTAL_MATERIAL = "experimental_material"
    SCIENTIFIC_DATA = "scientific_data"


class AssetRevisionState(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class AssetMemberRole(StrEnum):
    PRIMARY = "primary"
    PACKAGE = "package"
    EXTRACTED = "extracted"
    INDEX = "index"
    ATTACHMENT = "attachment"


class AssetContentMode(StrEnum):
    MANAGED = "managed"
    EXTERNAL = "external"
    GENERATED = "generated"
```

- [ ] **Step 4: Run the test and commit**

Run:

```bash
backend/.venv/bin/python -m pytest tests/test_governance_types.py -q
git add backend/app/core/governance.py tests/test_governance_types.py
git commit -m "feat: add research governance types"
```

Expected: PASS, then a successful commit.

## Task 2: Add Research Groups and Group Membership

**Files:**

- Create: `backend/app/models/research_group.py`
- Modify: `backend/app/models/project.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/app/schemas/research_group.py`
- Modify: `backend/app/schemas/project.py`
- Create: `backend/app/services/research_group_service.py`
- Create: `backend/app/api/research_groups.py`
- Modify: `backend/app/main.py`
- Test: `tests/test_research_groups.py`

- [ ] **Step 1: Write failing service and API tests**

Cover:

- An administrator can create a group.
- A PI can manage membership only for a group where the PI is an active `pi` member.
- A researcher cannot add themself to another group.
- A project must reference a group.
- The same user may have different roles in different groups.
- Archived groups and removed memberships do not satisfy group-scoped policy.

Use the exact role values `pi`, `postdoc`, `phd_student`, `assistant`, and `external_collaborator`.

- [ ] **Step 2: Run the tests and confirm failure**

```bash
backend/.venv/bin/python -m pytest tests/test_research_groups.py -q
```

Expected: FAIL because group models and routes are absent.

- [ ] **Step 3: Add the group models**

Implement these columns and constraints:

```python
class ResearchGroup(Base):
    __tablename__ = "research_groups"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )


class ResearchGroupMember(Base):
    __tablename__ = "research_group_members"
    __table_args__ = (
        UniqueConstraint("group_id", "user_id", name="uq_group_member"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    group_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_groups.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(32), index=True)
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

Add `research_group_id` to `Project` as an indexed nullable foreign key. A project may belong to zero or one group in V1. Creating, assigning, or changing the group is a PI/Admin action and produces an audit event in Phase 2.

- [ ] **Step 4: Add schemas, service, and routes**

Expose:

```text
POST   /api/v1/research-groups
GET    /api/v1/research-groups
GET    /api/v1/research-groups/{group_id}
PUT    /api/v1/research-groups/{group_id}
GET    /api/v1/research-groups/{group_id}/members
POST   /api/v1/research-groups/{group_id}/members
PUT    /api/v1/research-groups/{group_id}/members/{user_id}
DELETE /api/v1/research-groups/{group_id}/members/{user_id}
```

Validate role values in the Pydantic schema. Put authorization rules in `research_group_service.py`; route handlers must not duplicate them.

- [ ] **Step 5: Run tests and commit**

```bash
backend/.venv/bin/python -m pytest tests/test_research_groups.py tests/test_project_members.py tests/test_projects.py -q
git add backend/app/models/research_group.py backend/app/models/project.py backend/app/models/__init__.py backend/app/schemas/research_group.py backend/app/schemas/project.py backend/app/services/research_group_service.py backend/app/api/research_groups.py backend/app/main.py tests/test_research_groups.py
git commit -m "feat: add research group membership"
```

Expected: PASS and no regression in project membership tests.

## Task 3: Add the ResearchAsset, Revision, Member, and DataAsset Model

**Files:**

- Modify: `backend/app/models/research_asset.py`
- Create: `backend/app/models/asset_revision.py`
- Create: `backend/app/models/data_asset.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/schemas/research_asset.py`
- Create: `backend/app/schemas/asset_revision.py`
- Create: `backend/app/schemas/data_asset.py`
- Test: `tests/test_asset_revisions.py`
- Test: `tests/test_data_assets.py`

- [ ] **Step 1: Write failing model and schema tests**

Test:

- Every asset response contains category, classification, owner group, lifecycle, review status, safe catalog metadata, and current revision identity.
- Protected metadata is never returned by the catalog response schema.
- Every content-bearing asset has monotonically numbered immutable revisions.
- A revision contains one or more ordered members with normalized unique paths.
- Managed and generated members reference a Source; external members contain an encrypted reference and sanitized handoff metadata but no Source.
- A sealed revision cannot add, mutate, or delete members.
- `current_revision_id` can reference only a ready, sealed revision belonging to the same asset.
- A DataAsset has exactly one ResearchAsset.
- A ResearchAsset has at most one DataAsset.
- DataAsset contains scientific metadata but no storage locator or Source identity.

- [ ] **Step 2: Run the tests and confirm failure**

```bash
backend/.venv/bin/python -m pytest tests/test_asset_revisions.py tests/test_data_assets.py -q
```

Expected: FAIL because the new columns and model are absent.

- [ ] **Step 3: Add ResearchAsset governance columns**

Add:

```python
owning_group_id: Mapped[UUID | None] = mapped_column(
    ForeignKey("research_groups.id", ondelete="RESTRICT"), index=True
)
steward_user_id: Mapped[UUID | None] = mapped_column(
    ForeignKey("users.id", ondelete="RESTRICT"), index=True
)
asset_category: Mapped[str] = mapped_column(String(32), index=True)
classification: Mapped[str] = mapped_column(
    String(32), default=AssetClassification.CONFIDENTIAL, index=True
)
catalog_status: Mapped[str] = mapped_column(
    String(32), default=CatalogStatus.PUBLISHED, index=True
)
lifecycle_status: Mapped[str] = mapped_column(
    String(32), default=AssetLifecycleStatus.ACTIVE, index=True
)
governance_review_status: Mapped[str] = mapped_column(
    String(32), default=GovernanceReviewStatus.PENDING, index=True
)
catalog_metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
protected_metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
current_revision_id: Mapped[UUID | None] = mapped_column(
    ForeignKey("asset_revisions.id", ondelete="RESTRICT", use_alter=True),
    index=True,
)
catalog_published_at: Mapped[datetime | None] = mapped_column(
    DateTime(timezone=True)
)
catalog_withdrawn_at: Mapped[datetime | None] = mapped_column(
    DateTime(timezone=True)
)
```

Keep `visibility_scope` during the compatibility window. Mark it deprecated in schemas and stop using it for new policy decisions after Task 6.

- [ ] **Step 4: Add immutable revisions and content members**

Implement:

```python
class AssetRevision(Base):
    __tablename__ = "asset_revisions"
    __table_args__ = (
        UniqueConstraint(
            "research_asset_id",
            "revision_number",
            name="uq_asset_revision_number",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    research_asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_assets.id", ondelete="CASCADE"), index=True
    )
    revision_number: Mapped[int] = mapped_column(Integer)
    processing_state: Mapped[str] = mapped_column(
        String(24), default=AssetRevisionState.PENDING, index=True
    )
    manifest_sha256: Mapped[str | None] = mapped_column(String(64))
    change_summary: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    sealed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AssetContentMember(Base):
    __tablename__ = "asset_content_members"
    __table_args__ = (
        UniqueConstraint(
            "asset_revision_id",
            "normalized_path",
            name="uq_revision_member_path",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    asset_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("asset_revisions.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(24), index=True)
    content_mode: Mapped[str] = mapped_column(String(24), index=True)
    normalized_path: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text)
    media_type: Mapped[str | None] = mapped_column(String(128))
    format: Mapped[str] = mapped_column(String(32), index=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    sha256: Mapped[str | None] = mapped_column(String(64))
    managed_source_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("sources.id", ondelete="RESTRICT"), index=True
    )
    external_reference_ciphertext: Mapped[str | None] = mapped_column(Text)
    external_metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    external_handoff_json: Mapped[dict] = mapped_column(JSON, default=dict)
```

Enforce the member mode invariant in both service validation and database check constraints: `managed` and `generated` require `managed_source_id` and forbid external ciphertext; `external` requires ciphertext and forbids `managed_source_id`. External metadata may include URL or DOI catalog fields, but credentials and authorization headers are forbidden.

Revision members and manifest fields are immutable after `sealed_at` is set. A new upload, snapshot, generated document, saved memory, or saved conversation creates a new revision instead of mutating the current one.

- [ ] **Step 5: Add DataAsset specialization**

```python
class DataAsset(Base):
    __tablename__ = "data_assets"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    research_asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_assets.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    research_object_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_objects.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    data_type: Mapped[str] = mapped_column(String(64), index=True)
    data_modality: Mapped[str | None] = mapped_column(String(64), index=True)
    scientific_metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

`DataAsset` describes scientific semantics only. Physical and external content identity always belongs to an `AssetContentMember`, so a dataset may have BAM, BAI, README, and manifest members in one revision without duplicating storage fields.

- [ ] **Step 6: Add a revision service**

Create `backend/app/services/asset_revision_service.py` and extend `tests/test_asset_revisions.py`.

Required public contracts:

```python
async def create_revision(
    db: AsyncSession,
    *,
    asset: ResearchAsset,
    created_by: UUID,
    change_summary: str | None,
) -> AssetRevision

async def add_revision_member(
    db: AsyncSession,
    *,
    revision: AssetRevision,
    member: AssetMemberCreate,
) -> AssetContentMember

async def seal_revision(
    db: AsyncSession,
    *,
    asset: ResearchAsset,
    revision: AssetRevision,
) -> AssetRevision
```

Allocate `revision_number` while locking the ResearchAsset row. `seal_revision` validates every member, computes a deterministic manifest hash, sets `READY` and `sealed_at`, then updates `current_revision_id` in the same transaction. Failed candidate revisions remain non-current and retain only sanitized failure details.

- [ ] **Step 7: Run tests and commit**

```bash
backend/.venv/bin/python -m pytest tests/test_asset_revisions.py tests/test_data_assets.py tests/test_research_assets.py -q
git add backend/app/core/governance.py backend/app/models/research_asset.py backend/app/models/asset_revision.py backend/app/models/data_asset.py backend/app/models/__init__.py backend/app/schemas/research_asset.py backend/app/schemas/asset_revision.py backend/app/schemas/data_asset.py backend/app/services/asset_revision_service.py tests/test_asset_revisions.py tests/test_data_assets.py
git commit -m "feat: add versioned research assets"
```

Expected: PASS.

## Task 4: Add Access Policies and Agreements

**Files:**

- Create: `backend/app/models/access_policy.py`
- Create: `backend/app/models/data_use_agreement.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/app/schemas/access_policy.py`
- Test: `tests/test_access_policy_models.py`

- [ ] **Step 1: Write failing persistence tests**

Test explicit policy fields, optional exact-revision scope, enablement, priority, subject scopes, project conditions, and agreement linkage. Assert that a revision-specific policy never matches another revision and that an asset-wide policy matches future revisions only when `applies_to_future_revisions` is explicitly true.

- [ ] **Step 2: Run and confirm failure**

```bash
backend/.venv/bin/python -m pytest tests/test_access_policy_models.py -q
```

- [ ] **Step 3: Add the models**

Use an explicit policy row per subject and asset:

```python
class AccessPolicy(Base):
    __tablename__ = "access_policies"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    research_asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_assets.id", ondelete="CASCADE"), index=True
    )
    asset_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("asset_revisions.id", ondelete="CASCADE"), index=True
    )
    applies_to_future_revisions: Mapped[bool] = mapped_column(
        Boolean, default=False
    )
    subject_type: Mapped[str] = mapped_column(String(32), index=True)
    subject_id: Mapped[UUID | None] = mapped_column(index=True)
    group_role: Mapped[str | None] = mapped_column(String(32), index=True)
    required_project_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    required_agreement_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("data_use_agreements.id", ondelete="RESTRICT"), index=True
    )
    capabilities_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    effect: Mapped[str] = mapped_column(String(16), default="allow")
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    priority: Mapped[int] = mapped_column(Integer, default=0, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

Allowed `subject_type` values are `user`, `research_group`, `project`, and `group_role`. V1 uses explicit condition columns and does not accept executable expressions, arbitrary JSON logic, or user-authored policy code. Ordinary user grants set `asset_revision_id` and keep `applies_to_future_revisions=False`. Only a steward-created durable policy may opt into future revisions, and L4 policies must always target an exact revision. Idempotent migration policies are identified through deterministic IDs derived from the asset and legacy audience; ordinary policy creation always creates a distinct auditable policy row.

Create `DataUseAgreement` with `name`, `owning_group_id`, `status`, `valid_from`, `valid_until`, `allowed_project_id`, `allowed_research_group_id`, `allowed_capabilities_json`, `reference`, `created_by`, and timestamps. Do not store or parse contract text in this row.

- [ ] **Step 4: Run and commit**

```bash
backend/.venv/bin/python -m pytest tests/test_access_policy_models.py -q
git add backend/app/models/access_policy.py backend/app/models/data_use_agreement.py backend/app/models/__init__.py backend/app/schemas/access_policy.py tests/test_access_policy_models.py
git commit -m "feat: add governed access policies"
```

## Task 5: Create the Governance Migration and Backfill

**Files:**

- Create: `backend/alembic/versions/j0d1e2f3g4h5_add_governance_foundation.py`
- Create: `backend/app/services/governance_backfill.py`
- Test: `tests/test_governance_backfill.py`

- [ ] **Step 1: Write failing backfill tests**

Build fixtures containing:

- One asset for each legacy visibility scope.
- Owners, current project members, former project members, and existing SourceShare readers.
- Projects without research groups.

Assert:

- Existing project group links are preserved.
- Assets without an inferable project group remain unassigned and enter governance review.
- Classification mapping matches the roadmap.
- Every user who previously passed `can_user_read_asset` receives a migration policy with the required capabilities.
- Every migrated L1–L3 asset is discoverable through its classification baseline.
- Every content-bearing legacy asset has a sealed revision 1 and a member pointing to its existing Source.
- Existing datasets receive scientific metadata in DataAsset while their storage identity remains on the revision member.
- Collection-only legacy rows remain organizational catalog records and do not receive fake content revisions.
- Removed project members do not receive new compatibility access.
- Re-running the backfill creates no duplicate groups or policies.

- [ ] **Step 2: Run and confirm failure**

```bash
backend/.venv/bin/python -m pytest tests/test_governance_backfill.py -q
```

- [ ] **Step 3: Implement an idempotent backfill service**

Expose:

```python
@dataclass(frozen=True)
class GovernanceBackfillReport:
    groups_created: int
    projects_updated: int
    assets_updated: int
    policies_created: int
    revisions_created: int
    members_created: int
    unmatched_assets: tuple[UUID, ...]
```

Required public signature: `async def backfill_governance(db: AsyncSession, *, dry_run: bool) -> GovernanceBackfillReport`.

The implementation must:

1. Preserve existing configured project groups; never invent membership from project membership alone.
2. Infer `owning_group_id` only from an origin project that already has a configured research group.
3. Set `asset_category`, `steward_user_id`, classification, catalog status, lifecycle, review status, and minimal catalog metadata.
4. Create deterministic sealed revision 1 and content members from existing Source rows or immutable ResearchObject snapshots; do not create a revision for organizational collections.
5. Materialize deterministic revision-specific compatibility `AccessPolicy` rows that reproduce the legacy audience.
6. Create linked ResearchObject and DataAsset rows for existing assets with `asset_type="dataset"` while leaving storage identity on the content member.
7. Return unmatched asset IDs for the Admin governance-review queue without broadening access.

The complete compatibility capability set is:

```python
[
    Capability.METADATA_VIEW,
    Capability.CONTENT_PREVIEW,
    Capability.CONTENT_DOWNLOAD,
    Capability.CONTENT_USE_IN_AGENT,
]
```

Do not grant `asset:manage` through a compatibility content policy. Stewardship management is evaluated separately.

Apply that content set only to these legacy audiences:

- prior `lab_public`: all authenticated laboratory users;
- prior `lab_private`: PI/Admin users and already-linked project members;
- prior `project`: existing project members;
- prior `private`: the existing owner.

- [ ] **Step 4: Build the Alembic revision**

Set:

```python
revision = "j0d1e2f3g4h5"
down_revision = "i9c0d1e2f3g4"
```

The upgrade order is:

1. Create research-group tables.
2. Add nullable project and asset governance columns.
3. Create AssetRevision and AssetContentMember tables, add the deferred `current_revision_id` foreign key, then create DataAsset, DataUseAgreement, and AccessPolicy tables.
4. Backfill revision 1, members, category, scientific metadata, and revision-specific compatibility policies using logic deterministic on PostgreSQL and SQLite.
5. Add indexes, member-mode check constraints, revision uniqueness, and current-revision integrity triggers or service-enforced validation supported by both databases.

The downgrade must remove only the new structures. It must not rewrite legacy `visibility_scope`.

- [ ] **Step 5: Verify migration round trip**

Run against the test database:

```bash
backend/.venv/bin/python -m pytest tests/test_governance_backfill.py -q
cd backend && PYTHONPATH=. .venv/bin/alembic upgrade head
cd backend && PYTHONPATH=. .venv/bin/alembic downgrade -1
cd backend && PYTHONPATH=. .venv/bin/alembic upgrade head
```

Expected: all commands succeed.

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/j0d1e2f3g4h5_add_governance_foundation.py backend/app/services/governance_backfill.py tests/test_governance_backfill.py
git commit -m "feat: migrate assets into governance"
```

## Task 6: Replace Legacy Read Checks with a Policy Decision Service

**Files:**

- Create: `backend/app/services/access_policy_service.py`
- Modify: `backend/app/services/research_asset_service.py`
- Modify: `backend/app/services/sharing_service.py`
- Test: `tests/test_access_policy_service.py`
- Modify: `tests/test_research_assets.py`
- Modify: `tests/test_sharing.py`

- [ ] **Step 1: Write the policy matrix tests**

Cover at least:

| Case | Expected |
|---|---|
| Public asset discovery | Allow |
| Public content preview | Allow only through explicit public policy |
| Internal asset, active same-group member | Allow only matching capabilities |
| Confidential asset, project member without policy | Deny |
| Restricted asset, PI without policy | Deny |
| Top-secret asset, administrator without policy | Deny |
| Steward with `asset:manage` but no preview | Manage allowed, preview denied |
| Expired or revoked policy | Deny |
| Explicit deny and matching allow | Deny |
| Agent actor when policy allows only human actor | Deny |

- [ ] **Step 2: Run and confirm failure**

```bash
backend/.venv/bin/python -m pytest tests/test_access_policy_service.py -q
```

- [ ] **Step 3: Implement the decision contract**

```python
@dataclass(frozen=True)
class AccessContext:
    project_id: UUID | None = None
    asset_revision_id: UUID | None = None
    purpose: str | None = None
    actor_type: Literal["human", "agent"] = "human"
    agent_run_id: UUID | None = None
    agreement_ids: frozenset[UUID] = frozenset()


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    capability: Capability
    reason_code: str
    matched_policy_ids: tuple[UUID, ...] = ()
    grant_id: UUID | None = None
    requestable: bool = False
    required_approver_types: tuple[str, ...] = ()
    effective_capabilities: frozenset[Capability] = frozenset()
```

Required public signature: `async def authorize_asset(db: AsyncSession, *, user: User, asset: ResearchAsset, revision: AssetRevision | None, capability: Capability, context: AccessContext, now: datetime | None = None) -> PolicyDecision`.

Evaluation order:

1. Check asset existence, lifecycle, catalog state, revision lineage/state, and L4 discovery rules.
2. Apply explicit matching deny policies.
3. Apply the classification baseline.
4. Apply exact-revision policies, then explicitly future-applicable asset policies.
5. Validate active Data Use Agreement conditions.
6. Apply active grant capabilities, project, purpose, and dates.
7. Enforce Agent delegation restrictions.
8. Default deny and return a stable reason code without protected details.

Implement the classification baseline exactly:

- Public: all authenticated laboratory users receive metadata, preview, download, and Agent use under an explicit baseline policy; project context is optional.
- Internal: all laboratory users receive metadata; same owning-group members except External Collaborators receive preview and Agent use under an explicit baseline policy; project context is optional.
- Confidential: all laboratory users receive metadata; no default content capability.
- Restricted: all laboratory users receive metadata unless an explicit deny narrows it; no default content capability.
- Top Secret: hidden by default; only the steward, owning-group PIs, Admin governance users, and explicitly named subjects receive metadata. Agent use always requires an explicit grant.

For Confidential, Restricted, and Top Secret content capabilities, require a non-empty purpose, active project membership, project linkage, exact revision scope, and bounded validity. Metadata discovery remains possible without a project when the classification rule permits it.

Required reason codes:

```text
allowed_by_policy
asset_not_active
asset_not_discoverable
agreement_not_active
condition_not_met
explicitly_denied
inactive_user
no_matching_policy
grant_expired
```

- [ ] **Step 4: Turn old helpers into compatibility wrappers**

`can_user_read_asset` may remain temporarily to avoid a sweeping refactor, but it must call `authorize_asset(..., Capability.CONTENT_PREVIEW, ...)`. Remove role-based, owner-based, visibility-based, and project-link branches.

`can_user_manage_asset` must call `Capability.ASSET_MANAGE`.

`can_user_access_source` must resolve the source's ResearchAsset and call the policy service. A source without a materialized ResearchAsset must fail closed and emit an internal warning without exposing the source path.

- [ ] **Step 5: Run focused regressions**

```bash
backend/.venv/bin/python -m pytest tests/test_access_policy_service.py tests/test_research_assets.py tests/test_sharing.py -q
```

Expected: PASS. Update old tests whose expected access depended on implicit PI/Admin bypass to assert denial unless an explicit migration policy exists.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/access_policy_service.py backend/app/services/research_asset_service.py backend/app/services/sharing_service.py tests/test_access_policy_service.py tests/test_research_assets.py tests/test_sharing.py
git commit -m "feat: centralize research asset authorization"
```

## Task 7: Apply Governance Defaults During Asset Materialization

**Files:**

- Modify: `backend/app/services/research_asset_service.py`
- Modify: `backend/app/api/research_assets.py`
- Modify: `backend/app/schemas/research_asset.py`
- Test: `tests/test_research_asset_governance.py`

- [ ] **Step 1: Write failing default tests**

Assert:

- Personal upload defaults to `restricted`.
- Project or session upload defaults to `confidential`.
- Laboratory library upload defaults to `internal`.
- No upload defaults to `public` or `top_secret`.
- The owning group is derived from the project or selected active membership.
- The uploader is the initial steward.
- Every new L0–L3 asset receives its classification baseline for laboratory-wide `metadata:view`; L4 remains hidden by default.
- Only a user with `asset:manage` may change classification or protected metadata.
- Raising classification never silently expands permissions.
- Admin governance users can list migrated assets missing a group or steward without seeing protected metadata.

- [ ] **Step 2: Run and confirm failure**

```bash
backend/.venv/bin/python -m pytest tests/test_research_asset_governance.py -q
```

- [ ] **Step 3: Add an explicit creation context**

```python
@dataclass(frozen=True)
class AssetCreationContext:
    scope: Literal["personal", "project", "session", "library"]
    owning_group_id: UUID
    project_id: UUID | None = None


DEFAULT_CLASSIFICATION_BY_SCOPE = {
    "personal": AssetClassification.RESTRICTED,
    "project": AssetClassification.CONFIDENTIAL,
    "session": AssetClassification.CONFIDENTIAL,
    "library": AssetClassification.INTERNAL,
}
```

All materialization entry points must require this context. Do not infer `public` from legacy `lab_public`.

- [ ] **Step 4: Add governance update endpoint**

Add:

```text
PUT /api/v1/research-assets/{asset_id}/governance
GET /api/v1/research-assets/governance-review
```

The update schema accepts only classification, steward, lifecycle status, governance review status, catalog metadata, and protected metadata. The review queue is Admin-only, cursor-paginated, and returns only asset ID, safe title, owning-group state, steward state, and review status. The detail response uses the authorized schema; catalog list responses omit protected metadata.

- [ ] **Step 5: Run and commit**

```bash
backend/.venv/bin/python -m pytest tests/test_research_asset_governance.py tests/test_research_assets.py -q
git add backend/app/services/research_asset_service.py backend/app/api/research_assets.py backend/app/schemas/research_asset.py tests/test_research_asset_governance.py
git commit -m "feat: apply governance defaults to assets"
```

## Task 8: Phase Verification

- [ ] **Step 1: Run backend tests**

```bash
backend/.venv/bin/python -m pytest -q
```

Expected: PASS.

- [ ] **Step 2: Run repository checks**

```bash
git diff --check
pre-commit run
```

Expected: PASS. Fix any failure in the files changed by this phase.

- [ ] **Step 3: Review the migration report**

Run the backfill in dry-run mode through a short application command or an admin-only maintenance endpoint implemented in Task 5. Confirm:

- `unmatched_assets` is empty.
- Counts match source tables.
- No `public` or `top_secret` classification was assigned automatically.

- [ ] **Step 4: Create the phase checkpoint commit if needed**

If verification fixes changed files:

```bash
git add backend tests
git commit -m "test: verify governance foundation"
```

Otherwise do not create an empty commit.
