# Access Workflow and Content Gateway Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Use superpowers:test-driven-development before writing each production change.

**Goal:** Implement project-, purpose-, duration-, and revision-bound access requests, multi-step approval, expiring grants, revocation, immutable audit records, and a fail-closed member content gateway for every protected content path.

**Architecture:** Workflow state is persisted in `AccessRequest`, `AccessApprovalStep`, and immutable `AccessGrant` rows that target an exact AssetRevision. Durable AccessPolicy rules remain separate from approved individual grants. All raw files, member previews, extracted text, and external handoffs are accessed through `ResearchContentGateway`, which validates asset/revision/member lineage, authorizes immediately before reading, and emits an audit event for allow or deny.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic V2, Alembic, PostgreSQL/SQLite, local file storage, cryptography, pytest.

---

## Task 1: Add Request, Approval, Grant, and Audit Models

**Files:**

- Create: `backend/app/models/access_request.py`
- Create: `backend/app/models/access_audit.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/k1e2f3g4h5i6_add_access_workflow.py`
- Test: `tests/test_access_workflow_models.py`

- [ ] **Step 1: Write failing persistence tests**

Cover:

- A request belongs to one user, one asset, one immutable revision, and a required project for L2–L4 content.
- Duration must produce an expiration timestamp after approval.
- Approval steps have stable sequence numbers.
- A grant links back to exactly one approved request.
- Audit rows can survive user or asset retirement.

- [ ] **Step 2: Run and confirm failure**

```bash
backend/.venv/bin/python -m pytest tests/test_access_workflow_models.py -q
```

Expected: FAIL because the models do not exist.

- [ ] **Step 3: Add workflow models**

Use these stable state values:

```python
class AccessRequestStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    PENDING_OWNER = "pending_owner"
    PENDING_PI = "pending_pi"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class ApprovalStepStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SKIPPED = "skipped"
```


Implement:

```python
class AccessRequest(Base):
    __tablename__ = "access_requests"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    research_asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_assets.id", ondelete="CASCADE"), index=True
    )
    asset_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("asset_revisions.id", ondelete="RESTRICT"), index=True
    )
    requester_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    project_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    purpose: Mapped[str] = mapped_column(Text)
    hypothesis_object_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("research_objects.id", ondelete="SET NULL"), index=True
    )
    requested_capabilities: Mapped[list[str]] = mapped_column(JSON)
    requested_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    requested_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(24), default=AccessRequestStatus.DRAFT, index=True
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AccessApprovalStep(Base):
    __tablename__ = "access_approval_steps"
    __table_args__ = (
        UniqueConstraint(
            "access_request_id",
            "sequence",
            name="uq_request_step_sequence",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    access_request_id: Mapped[UUID] = mapped_column(
        ForeignKey("access_requests.id", ondelete="CASCADE"), index=True
    )
    step_type: Mapped[str] = mapped_column(String(24), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    eligible_subject_json: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(
        String(24), default=ApprovalStepStatus.PENDING, index=True
    )
    decided_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    decision_comment: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AccessGrant(Base):
    __tablename__ = "access_grants"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    research_asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_assets.id", ondelete="RESTRICT"), index=True
    )
    asset_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("asset_revisions.id", ondelete="RESTRICT"), index=True
    )
    grantee_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), index=True
    )
    access_request_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("access_requests.id", ondelete="RESTRICT"), index=True
    )
    purpose: Mapped[str] = mapped_column(Text)
    hypothesis_object_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("research_objects.id", ondelete="SET NULL"), index=True
    )
    capabilities_json: Mapped[list[str]] = mapped_column(JSON)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    granted_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    grant_reason: Mapped[str] = mapped_column(Text)
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    revoked_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    revocation_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

Grant status is derived as `scheduled`, `active`, `expired`, or `revoked`; do not persist a mutable status column. Grant capabilities, revision, project, purpose, and dates are immutable. A change requires revocation and a new grant. `access_request_id` is nullable for proactive L4 grants, but proactive L4 grants still require an exact revision, project, purpose, and bounded duration.

- [ ] **Step 4: Add the audit model**

`AccessAuditEvent` stores `research_asset_id`, `asset_revision_id`, optional `asset_content_member_id`, actor, project, capability, action, outcome, reason code, request/grant identity, timestamp, and an allowlisted details object.

- nullable actor user ID, actor type (`human`, `agent`, or `system`), and agent run ID;
- asset, revision, optional member, and project IDs;
- action, capability, decision (`allow`, `deny`, or `not_applicable`), and reason code;
- request ID, grant ID, policy IDs;
- timestamp and a `context_json` field containing only allowlisted non-sensitive identifiers and decision context.

Use `ondelete="SET NULL"` for user, asset, project, request, and grant foreign keys so audit history remains. Do not make audit rows mutable through an API.

- [ ] **Step 5: Add the migration**

Set:

```python
revision = "k1e2f3g4h5i6"
down_revision = "j0d1e2f3g4h5"
```

Create indexes on request status, requester, asset/revision, grant asset/revision/project/expiration, audit actor, audit asset/revision/member, and audit timestamp. Add composite constraints that prevent an AccessRequest or AccessGrant from pairing an asset with a revision owned by another asset.

- [ ] **Step 6: Run and commit**

```bash
backend/.venv/bin/python -m pytest tests/test_access_workflow_models.py -q
git add backend/app/models/access_request.py backend/app/models/access_audit.py backend/app/models/__init__.py backend/alembic/versions/k1e2f3g4h5i6_add_access_workflow.py tests/test_access_workflow_models.py
git commit -m "feat: add access workflow persistence"
```

## Task 2: Encrypt and Resolve External Content-Member References

**Files:**

- Modify: `backend/app/core/config.py`
- Modify: `.env.template`
- Create: `backend/app/services/locator_crypto.py`
- Create: `backend/app/services/external_member_reference_service.py`
- Test: `tests/test_external_member_reference.py`

- [ ] **Step 1: Write failing encryption tests**

Test:

- Stored ciphertext differs from a local storage key.
- Encryption and decryption round trip.
- Wrong key fails with a generic internal error.
- Logs and `repr()` do not contain plaintext.
- Missing key prevents application use of locator content.

- [ ] **Step 2: Run and confirm failure**

```bash
backend/.venv/bin/python -m pytest tests/test_external_member_reference.py -q
```

- [ ] **Step 3: Add configuration**

Add:

```python
research_asset_locator_key: SecretStr | None = Field(
    default=None,
    validation_alias="OPENCOLAB_RESEARCH_ASSET_LOCATOR_KEY",
)
```

Document in `.env.template` that the value must be a URL-safe 32-byte base64 Fernet key and must be injected through the environment or secret manager. Never commit a real key.

- [ ] **Step 4: Implement encryption**

Use `cryptography.fernet.Fernet`, which is already provided transitively by the backend security dependencies. If dependency inspection shows it is not directly declared, add a bounded `cryptography` dependency to all backend requirement variants before importing it.

Expose:

```python
class LocatorCryptoError(RuntimeError):
    pass


class LocatorCrypto:
    def __init__(self, key: SecretStr) -> None:
        self._fernet = Fernet(key.get_secret_value().encode("ascii"))

    def encrypt(self, locator: str) -> str:
        return self._fernet.encrypt(locator.encode("utf-8")).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise LocatorCryptoError("Unable to resolve protected locator") from exc
```

Never log `locator` or `ciphertext`.

The service writes ciphertext into `AssetContentMember.external_reference_ciphertext`. It may resolve a URL, DOI landing page, or controlled external-system identifier only after gateway authorization. It returns only sanitized `external_handoff_json` or a server-side fetch result; it never returns ciphertext, decrypted references, credentials, authorization headers, or signed URLs to the client.

- [ ] **Step 5: Run and commit**

```bash
backend/.venv/bin/python -m pytest tests/test_external_member_reference.py -q
git add backend/app/core/config.py .env.template backend/app/services/locator_crypto.py backend/app/services/external_member_reference_service.py tests/test_external_member_reference.py
git commit -m "feat: protect research asset locators"
```

## Task 3: Implement Approval Policy Resolution

**Files:**

- Create: `backend/app/services/approval_policy_service.py`
- Test: `tests/test_approval_policy_service.py`

- [ ] **Step 1: Write the failing classification matrix**

Assert these V1 approval paths:

| Classification | Required step |
|---|---|
| Public | No request for baseline public capabilities |
| Internal, same owning group and not external collaborator | No request for baseline preview and Agent use |
| Internal, cross-group or external collaborator | Asset Owner |
| Confidential | Asset Owner or owning-group PI |
| Restricted | Asset Owner and owning-group PI, with distinct users |
| Top secret | Ordinary request unavailable; proactive PI/Admin governance grant only |

Also test:

- If the Asset Owner is the only owning-group PI for a Restricted asset, an Admin governance user supplies the distinct second decision.
- Agreement-required policy adds agreement validation before grant.
- A Restricted request never lets one user satisfy both steps.
- Missing eligible approver makes submission fail with `approval_route_unavailable`.

- [ ] **Step 2: Run and confirm failure**

```bash
backend/.venv/bin/python -m pytest tests/test_approval_policy_service.py -q
```

- [ ] **Step 3: Implement the resolver**

```python
@dataclass(frozen=True)
class ApprovalStepDefinition:
    sequence: int
    step_type: Literal["asset_owner", "group_pi"]
    eligible_subject: Mapping[str, str]
```

Required public signature: `async def resolve_approval_steps(db: AsyncSession, *, requester: User, asset: ResearchAsset, revision: AssetRevision, project: Project, capabilities: frozenset[Capability]) -> tuple[ApprovalStepDefinition, ...]`.

Persist the returned snapshot with the request. Do not dynamically rewrite pending steps when membership changes; instead prevent an inactive approver from acting and allow a PI to reassign the pending step with an audit event.

- [ ] **Step 4: Run and commit**

```bash
backend/.venv/bin/python -m pytest tests/test_approval_policy_service.py -q
git add backend/app/services/approval_policy_service.py tests/test_approval_policy_service.py
git commit -m "feat: resolve data approval routes"
```

## Task 4: Implement the Access Request State Machine

**Files:**

- Create: `backend/app/schemas/access_request.py`
- Create: `backend/app/services/access_request_service.py`
- Test: `tests/test_access_request_service.py`

- [ ] **Step 1: Write failing state-machine tests**

Cover:

- Create a draft with exact revision, purpose, project, optional hypothesis, capabilities, and requested dates, then submit it.
- Reject blank or overlong purpose.
- Reject content request when metadata visibility is denied.
- Require requester membership in the selected project.
- Enforce maximum duration: 90 days for Internal/Confidential and 30 days for Restricted.
- Reject ordinary Top Secret requests.
- Prevent duplicate overlapping pending requests for the same requester, revision, project, and capabilities.
- Approve steps only in sequence.
- Reject ends the workflow and creates no grant.
- Final approval atomically creates one immutable AccessGrant.
- Cancel is requester-only and pending-only.
- Revocation writes revocation fields without mutating capabilities or dates.
- Expiration denies immediately even before a cleanup job updates stored status.
- Reclassification to a stricter level suspends incompatible active grants.

- [ ] **Step 2: Run and confirm failure**

```bash
backend/.venv/bin/python -m pytest tests/test_access_request_service.py -q
```

- [ ] **Step 3: Implement commands with row locking**

Required public signatures:

- `async def create_access_request(db: AsyncSession, *, requester: User, asset_id: UUID, revision_id: UUID, project_id: UUID, purpose: str, capabilities: frozenset[Capability], requested_start_at: datetime, requested_end_at: datetime, hypothesis_object_id: UUID | None) -> AccessRequest`
- `async def submit_access_request(db: AsyncSession, *, requester: User, request_id: UUID) -> AccessRequest`
- `async def decide_approval_step(db: AsyncSession, *, approver: User, request_id: UUID, approve: bool, reason: str | None) -> AccessRequest`
- `async def revoke_access_grant(db: AsyncSession, *, actor: User, grant_id: UUID, reason: str) -> AccessGrant`

Use `SELECT ... FOR UPDATE` for decision and revocation transitions. Re-read the current step and current user membership inside the transaction. A duplicate decision returns the existing terminal result only when it has the same decision and actor; otherwise return conflict.

The generated grant:

- references the asset, exact revision, requester, selected project, and approved request;
- contains exactly the approved capabilities;
- copies the immutable purpose and optional hypothesis;
- uses the approved start and end dates;
- records the final approver and a safe grant reason.

Approvers may remove requested capabilities but cannot add new ones. `asset:manage` is not requestable through this workflow.

- [ ] **Step 4: Run and commit**

```bash
backend/.venv/bin/python -m pytest tests/test_access_request_service.py -q
git add backend/app/schemas/access_request.py backend/app/services/access_request_service.py tests/test_access_request_service.py
git commit -m "feat: implement access request workflow"
```

## Task 5: Add Audit Service with Fail-Closed Content Auditing

**Files:**

- Create: `backend/app/services/access_audit_service.py`
- Test: `tests/test_access_audit_service.py`

- [ ] **Step 1: Write failing audit tests**

Assert:

- Allow and deny decisions produce events.
- Details reject unknown keys.
- Storage paths, extracted text, purpose text, and protected metadata are never stored.
- A content operation fails closed if its mandatory audit write fails.
- Catalog discovery can return a generic failure if audit storage is unavailable.
- Audit rows cannot be updated or deleted through service functions.

- [ ] **Step 2: Run and confirm failure**

```bash
backend/.venv/bin/python -m pytest tests/test_access_audit_service.py -q
```

- [ ] **Step 3: Add an allowlisted audit event writer**

```python
ALLOWED_AUDIT_DETAIL_KEYS = frozenset(
    {
        "classification",
        "content_kind",
        "result_count",
        "source",
    }
)
```

Required public signature: `async def record_access_event(db: AsyncSession, *, actor: User, asset_id: UUID | None, revision_id: UUID | None, member_id: UUID | None, project_id: UUID | None, action: str, capability: Capability | None, decision: Literal["allow", "deny", "not_applicable"], reason_code: str, request_id: UUID | None = None, grant_id: UUID | None = None, details: Mapping[str, str | int | bool] | None = None) -> AccessAuditEvent`.

Do not store raw IP, user-agent, request purpose, policy conditions, or protected values.

- [ ] **Step 4: Run and commit**

```bash
backend/.venv/bin/python -m pytest tests/test_access_audit_service.py -q
git add backend/app/services/access_audit_service.py tests/test_access_audit_service.py
git commit -m "feat: add governed access audit"
```

## Task 6: Build the Protected Content Gateway

**Files:**

- Create: `backend/app/services/research_content_gateway.py`
- Modify: `backend/app/services/file_storage.py`
- Test: `tests/test_research_content_gateway.py`

- [ ] **Step 1: Write failing gateway tests**

Test every content kind:

- Raw file stream requires `content:download`.
- Preview requires `content:preview`.
- Extracted text for a human requires `content:preview`.
- Extracted chunks for an agent require `content:use_in_agent`.
- Asset, revision, and member IDs must belong to the same lineage.
- A grant for revision 1 cannot read revision 2 or any revision 2 member.
- Expired, revoked, inactive, or classification-invalid grant is denied.
- Content is not opened before authorization.
- Authorization is rechecked after locator resolution and before streaming.
- Allow and deny paths are audited.

- [ ] **Step 2: Run and confirm failure**

```bash
backend/.venv/bin/python -m pytest tests/test_research_content_gateway.py -q
```

- [ ] **Step 3: Implement the gateway contract**

```python
@dataclass(frozen=True)
class AuthorizedContent:
    asset_id: UUID
    revision_id: UUID
    member_id: UUID
    content_kind: Literal["raw_file", "preview", "extracted_text", "chunks"]
    media_type: str
    filename: str | None
    payload: bytes | str | Sequence[Chunk]


class ResearchContentGateway:
    read: Callable[..., Awaitable[AuthorizedContent]]
```

Required public signature: `async def read(self, *, db: AsyncSession, user: User, asset_id: UUID, revision_id: UUID, member_id: UUID, capability: Capability, content_kind: ContentKind, context: AccessContext) -> AuthorizedContent`.

The method order is mandatory:

1. Load asset, immutable revision, member lineage, and only the fields required for policy evaluation.
2. Authorize the exact revision.
3. Record denial and stop, or continue.
4. Resolve the member's managed Source or authorized external reference handoff.
5. Load managed content from the existing storage abstraction, or return only sanitized external handoff instructions.
6. Recheck asset lifecycle and policy expiry.
7. Record allow.
8. Return the content wrapper.

Never return a filesystem path, external reference, or credential. For managed streaming, return an opened file object or iterator owned by the response lifecycle. Collections and revisions without members are never readable through this gateway.

- [ ] **Step 4: Run and commit**

```bash
backend/.venv/bin/python -m pytest tests/test_research_content_gateway.py -q
git add backend/app/services/research_content_gateway.py backend/app/services/file_storage.py tests/test_research_content_gateway.py
git commit -m "feat: gate protected research content"
```

## Task 7: Route Existing Source Content Through the Gateway

**Files:**

- Modify: `backend/app/api/sources.py`
- Modify: `backend/app/services/sharing_service.py`
- Modify: `backend/app/services/research_asset_service.py`
- Modify: `tests/test_sharing.py`
- Create: `tests/test_source_content_authorization.py`

- [ ] **Step 1: Write endpoint regression tests**

Cover:

- `/sources/{id}` returns safe metadata only.
- `/sources/{id}/file` uses `content:download`.
- `/sources/{id}/thumbnail` uses `content:preview`.
- `/sources/{id}/extraction` uses `content:preview`.
- Query tokens do not bypass live authorization.
- Admin, PI, project member, and owner are denied without policy.
- Denied responses are `403` with a generic localized code.
- Missing ResearchAsset fails closed.

- [ ] **Step 2: Run and confirm failure**

```bash
backend/.venv/bin/python -m pytest tests/test_source_content_authorization.py -q
```

- [ ] **Step 3: Replace direct content reads**

Resolve `Source.id -> AssetContentMember.managed_source_id -> AssetRevision -> ResearchAsset`, then call `ResearchContentGateway` with all three identities. Remove direct file-path `FileResponse` creation from the route. Preserve range and download behavior through a streaming response that never exposes the path.

Keep token validation only as request authentication where already required; it must not replace policy authorization.

Replace exception text such as:

```python
f"File processing failed: {exc}"
```

with a stable internal log message and a generic client error code. Use `logger.exception` without including file path, protected metadata, or extracted content.

- [ ] **Step 4: Run and commit**

```bash
backend/.venv/bin/python -m pytest tests/test_source_content_authorization.py tests/test_sharing.py tests/test_source_extractions.py -q
git add backend/app/api/sources.py backend/app/services/sharing_service.py backend/app/services/research_asset_service.py tests/test_source_content_authorization.py tests/test_sharing.py
git commit -m "feat: enforce source content gateway"
```

## Task 8: Expose Policy, Access, Content, and Audit APIs

**Files:**

- Create: `backend/app/api/access_requests.py`
- Create: `backend/app/api/access_policies.py`
- Create: `backend/app/api/data_use_agreements.py`
- Create: `backend/app/api/research_content.py`
- Create: `backend/app/api/access_audit.py`
- Modify: `backend/app/main.py`
- Test: `tests/test_access_request_api.py`

- [ ] **Step 1: Write failing API tests**

Test authorization, pagination, validation, optimistic-conflict responses, L4 non-disclosure, and safe response shapes for:

```text
GET    /api/v1/access-requests
POST   /api/v1/access-requests
GET    /api/v1/access-requests/{request_id}
POST   /api/v1/access-requests/{request_id}/submit
POST   /api/v1/access-requests/{request_id}/cancel
POST   /api/v1/access-requests/{request_id}/decision
GET    /api/v1/access-grants
POST   /api/v1/access-grants/proactive
POST   /api/v1/access-grants/{grant_id}/revoke
GET    /api/v1/research-assets/{asset_id}/policies
POST   /api/v1/research-assets/{asset_id}/policies
PUT    /api/v1/research-assets/{asset_id}/policies/{policy_id}
POST   /api/v1/research-assets/{asset_id}/policies/{policy_id}/disable
GET    /api/v1/data-use-agreements
POST   /api/v1/data-use-agreements
PUT    /api/v1/data-use-agreements/{agreement_id}
GET    /api/v1/research-assets/{asset_id}/protected-metadata
GET    /api/v1/research-assets/{asset_id}/revisions/{revision_id}/members/{member_id}/content
GET    /api/v1/research-assets/{asset_id}/revisions/{revision_id}/members/{member_id}/download
GET    /api/v1/asset-access-audit
```

List endpoints use cursor pagination with default 20 and maximum 100. `GET /access-requests` supports `mine`, `pending_my_approval`, and status filters. L4 unauthorized lookup returns `404`, not `403`. Proactive grants are limited to eligible L4 group PIs and Admin governance users, require exact revision, project, purpose, and reason, and last at most 30 days.

- [ ] **Step 2: Run and confirm failure**

```bash
backend/.venv/bin/python -m pytest tests/test_access_request_api.py -q
```

- [ ] **Step 3: Implement thin routes**

Routes authenticate, validate schemas, call the service, and translate stable service exceptions into:

```text
400 invalid_request
403 access_denied
404 not_found
409 state_conflict
422 validation_error
```

Do not expose approver eligibility details to unauthorized callers.

- [ ] **Step 4: Run and commit**

```bash
backend/.venv/bin/python -m pytest tests/test_access_request_api.py -q
git add backend/app/api/access_requests.py backend/app/api/access_policies.py backend/app/api/data_use_agreements.py backend/app/api/research_content.py backend/app/api/access_audit.py backend/app/main.py tests/test_access_request_api.py
git commit -m "feat: expose research access workflow"
```

## Task 9: Add Expiry and Reclassification Enforcement

**Files:**

- Create: `backend/app/services/access_grant_maintenance.py`
- Modify: `backend/app/services/access_policy_service.py`
- Modify: `backend/app/services/research_asset_service.py`
- Test: `tests/test_access_grant_lifecycle.py`

- [ ] **Step 1: Write failing lifecycle tests**

Test:

- A policy or grant is denied at `valid_until` even before expiry detection is audited.
- Maintenance emits one expiry-detected audit event per newly observed expired grant without mutating immutable grant dates or capabilities.
- Revocation is immediately visible.
- Raising classification revalidates and revokes grants that no longer meet the route.
- Lowering classification does not auto-grant new capabilities.
- Publishing a new current revision does not rewrite or extend an older revision grant.
- Catalog withdrawal removes ordinary discovery, and asset archival denies all content capabilities.

- [ ] **Step 2: Run and confirm failure**

```bash
backend/.venv/bin/python -m pytest tests/test_access_grant_lifecycle.py -q
```

- [ ] **Step 3: Implement batch maintenance**

Required public signature: `async def expire_access_grants(db: AsyncSession, *, now: datetime, batch_size: int = 500) -> int`.

The function records expiry detection and returns the count. Call it from the existing worker startup or maintenance loop only if such a loop already exists. If no scheduler exists, expose it as an admin maintenance command and rely on live grant-time evaluation for correctness.

- [ ] **Step 4: Run and commit**

```bash
backend/.venv/bin/python -m pytest tests/test_access_grant_lifecycle.py -q
git add backend/app/services/access_grant_maintenance.py backend/app/services/access_policy_service.py backend/app/services/research_asset_service.py tests/test_access_grant_lifecycle.py
git commit -m "feat: enforce access grant lifecycle"
```

## Task 10: Phase Verification

- [ ] **Step 1: Run access and source suites**

```bash
backend/.venv/bin/python -m pytest tests/test_access_policy_service.py tests/test_access_request_service.py tests/test_access_request_api.py tests/test_research_content_gateway.py tests/test_source_content_authorization.py tests/test_access_grant_lifecycle.py -q
```

Expected: PASS.

- [ ] **Step 2: Run all backend tests and checks**

```bash
backend/.venv/bin/python -m pytest -q
git diff --check
pre-commit run
```

Expected: PASS.

- [ ] **Step 3: Verify no bypass remains**

Run:

```bash
rg -n "can_user_access_source|can_user_read_asset|FileResponse|open\\(" backend/app
```

Inspect each result. Any protected file or extracted-content read outside `ResearchContentGateway` must be removed or explicitly documented as a non-content metadata operation.

- [ ] **Step 4: Create a phase checkpoint commit only if needed**

```bash
git add backend tests .env.template
git commit -m "test: verify governed content access"
```

Do not create an empty commit.
