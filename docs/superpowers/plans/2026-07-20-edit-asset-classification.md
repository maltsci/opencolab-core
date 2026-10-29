# Edit Existing Asset Classification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a permission-aware classification change modal to existing Research Assets while preserving catalog and protected-metadata boundaries.

**Architecture:** A dedicated backend helper evaluates classification-change authority independently from general asset management. A dedicated classification endpoint validates transitions, records a protected change history, and returns a safe catalog response. A focused React modal performs the interaction from the asset detail drawer, while laboratory and project pages refresh their local state after success.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async ORM, Pydantic V2, pytest, React 19, TypeScript 5.9, Ant Design 6, i18next, Axios.

---

## File Map

- Modify `backend/app/services/research_asset_service.py`: dedicated classification-change authorization helper.
- Modify `backend/app/schemas/research_asset.py`: request model and response capability field.
- Modify `backend/app/api/research_assets.py`: capability serialization and dedicated classification endpoint.
- Modify `tests/test_research_asset_governance.py`: permission, transition, protected-history, and response-boundary tests.
- Create `frontend/src/components/library/ClassificationChangeModal.tsx`: modal state, validation, request, and error handling.
- Modify `frontend/src/components/library/AssetDetailDrawer.tsx`: permission-aware trigger and modal integration.
- Modify `frontend/src/types/research-asset.ts`: response capability typing.
- Modify `frontend/src/pages/Library.tsx`: refresh the selected asset and laboratory list.
- Modify `frontend/src/pages/ProjectAssets.tsx`: refresh the selected asset and project list.
- Modify `frontend/src/locales/en-US.json`: English interaction copy.
- Modify `frontend/src/locales/zh-CN.json`: Chinese interaction copy.

### Task 1: Add Dedicated Classification Authority

**Files:**
- Modify: `tests/test_research_asset_governance.py`
- Modify: `backend/app/services/research_asset_service.py`
- Modify: `backend/app/schemas/research_asset.py`
- Modify: `backend/app/api/research_assets.py`

- [ ] **Step 1: Write failing permission tests**

Add imports:

```python
from app.models.research_group import ResearchGroup, ResearchGroupMember
from app.services.research_asset_service import can_user_change_classification
```

Add focused tests that use real group membership rows:

```python
async def test_classification_authority_matches_owner_steward_group_pi_and_admin(
    db: AsyncSession,
    admin_user: User,
    pi_user: User,
    researcher_user: User,
) -> None:
    group = ResearchGroup(name="Classification Lab", created_by=admin_user.id)
    steward = User(
        username="classification-steward",
        hashed_password="not-used-in-service-test",
        role="researcher",
    )
    db.add_all([group, steward])
    await db.flush()
    db.add(
        ResearchGroupMember(
            group_id=group.id,
            user_id=pi_user.id,
            role="pi",
            created_by=admin_user.id,
        )
    )
    asset = ResearchAsset(
        asset_type="uploaded_file",
        title="Controlled dataset",
        owner_id=researcher_user.id,
        steward_user_id=steward.id,
        owning_group_id=group.id,
        classification="confidential",
    )
    db.add(asset)
    await db.flush()

    assert await can_user_change_classification(db, researcher_user, asset)
    assert await can_user_change_classification(db, steward, asset)
    assert await can_user_change_classification(db, pi_user, asset)
    assert await can_user_change_classification(db, admin_user, asset)


async def test_classification_authority_rejects_other_group_pi_and_ordinary_member(
    db: AsyncSession,
    admin_user: User,
    pi_user: User,
    researcher_user: User,
) -> None:
    owning_group = ResearchGroup(name="Owning Lab", created_by=admin_user.id)
    other_group = ResearchGroup(name="Other Lab", created_by=admin_user.id)
    db.add_all([owning_group, other_group])
    await db.flush()
    db.add_all(
        [
            ResearchGroupMember(
                group_id=other_group.id,
                user_id=pi_user.id,
                role="pi",
                created_by=admin_user.id,
            ),
            ResearchGroupMember(
                group_id=owning_group.id,
                user_id=researcher_user.id,
                role="member",
                created_by=admin_user.id,
            ),
        ]
    )
    asset = ResearchAsset(
        asset_type="uploaded_file",
        title="Other group dataset",
        owning_group_id=owning_group.id,
        classification="confidential",
    )
    db.add(asset)
    await db.flush()

    assert not await can_user_change_classification(db, pi_user, asset)
    assert not await can_user_change_classification(db, researcher_user, asset)


async def test_global_pi_cannot_change_ungrouped_legacy_asset(
    db: AsyncSession,
    pi_user: User,
) -> None:
    asset = ResearchAsset(
        asset_type="uploaded_file",
        title="Ungrouped legacy asset",
        classification="internal",
    )
    db.add(asset)
    await db.flush()

    assert not await can_user_change_classification(db, pi_user, asset)


async def test_catalog_and_detail_report_classification_authority(
    client: AsyncClient,
    researcher_headers: dict,
    researcher_user: User,
    db: AsyncSession,
) -> None:
    source = Source(
        type="file",
        name="owner-catalog.pdf",
        owner_id=researcher_user.id,
        processing_state="ready",
    )
    db.add(source)
    await db.flush()
    asset = await materialize_source_asset(
        db=db,
        source=source,
        owner_id=researcher_user.id,
        origin_project_id=None,
        origin_session_id=None,
        visibility_scope="lab_public",
        link_type="source",
    )
    await db.commit()

    catalog = await client.get(
        "/api/v1/library/assets",
        headers=researcher_headers,
    )
    detail = await client.get(
        f"/api/v1/research-assets/{asset.id}",
        headers=researcher_headers,
    )

    assert catalog.status_code == 200
    catalog_asset = next(
        item for item in catalog.json() if item["id"] == asset.id
    )
    assert catalog_asset["can_change_classification"] is True
    assert detail.status_code == 200
    assert detail.json()["can_change_classification"] is True
```

- [ ] **Step 2: Run the permission tests and verify RED**

Run:

```bash
OPENCOLAB_DATABASE_URL='sqlite+aiosqlite:///./tmp/settings.db' \
backend/.venv/bin/python -c 'import os, sys, pytest; code=pytest.main([
  "-q",
  "tests/test_research_asset_governance.py",
  "-k", "classification_authority or global_pi_cannot",
  "--tb=short",
]); sys.stdout.flush(); sys.stderr.flush(); os._exit(code)'
```

Expected: collection/import failure because
`can_user_change_classification` does not exist.

- [ ] **Step 3: Implement the dedicated authorization helper**

In `backend/app/services/research_asset_service.py`, add imports:

```python
from app.core.constants import ROLE_ADMIN, ROLE_PI, ROLES_ALL
from app.services.research_group_service import is_active_group_member
```

Add the helper near the existing authorization helpers:

```python
async def can_user_change_classification(
    db: AsyncSession,
    user: User,
    asset: ResearchAsset,
) -> bool:
    if user.role not in ROLES_ALL:
        return False
    if user.role == ROLE_ADMIN:
        return True
    if user.id in {asset.owner_id, asset.steward_user_id}:
        return True
    if asset.owning_group_id is None or user.role != ROLE_PI:
        return False
    return await is_active_group_member(
        db,
        group_id=asset.owning_group_id,
        user_id=user.id,
        role="pi",
    )
```

- [ ] **Step 4: Add the capability to safe and authorized responses**

In both `ResearchAssetResponse` and `ResearchAssetCatalogListResponse` in
`backend/app/schemas/research_asset.py`, add:

```python
can_change_classification: bool = False
```

Import the helper in `backend/app/api/research_assets.py`:

```python
from app.services.research_asset_service import can_user_change_classification
```

Set the capability in both `_response` and `_catalog_response`:

```python
payload["can_change_classification"] = (
    await can_user_change_classification(db, user, asset)
)
```

- [ ] **Step 5: Verify GREEN**

Run:

```bash
OPENCOLAB_DATABASE_URL='sqlite+aiosqlite:///./tmp/settings.db' \
backend/.venv/bin/python -c 'import os, sys, pytest; code=pytest.main([
  "-q",
  "tests/test_research_asset_governance.py",
  "-k", "classification_authority or global_pi_cannot",
  "--tb=short",
]); sys.stdout.flush(); sys.stderr.flush(); os._exit(code)'
```

Expected: `4 passed`, including distinct owner and steward assertions and
response capability serialization.

- [ ] **Step 6: Commit the authority boundary**

```bash
git add \
  backend/app/services/research_asset_service.py \
  backend/app/schemas/research_asset.py \
  backend/app/api/research_assets.py \
  tests/test_research_asset_governance.py
git commit -m "feat: expose classification change authority"
```

### Task 2: Add the Safe Classification Endpoint

**Files:**
- Modify: `tests/test_research_asset_governance.py`
- Modify: `backend/app/schemas/research_asset.py`
- Modify: `backend/app/api/research_assets.py`

- [ ] **Step 1: Write failing endpoint tests**

Add the following behavior tests. Use `create_access_token` to build headers for
new users created inside a test:

```python
from app.core.security import create_access_token
```

```python
async def test_owner_can_raise_classification_without_reason(
    client: AsyncClient,
    researcher_headers: dict,
    researcher_user: User,
    db: AsyncSession,
) -> None:
    asset = ResearchAsset(
        asset_type="uploaded_file",
        title="Owner dataset",
        owner_id=researcher_user.id,
        steward_user_id=researcher_user.id,
        classification="internal",
        protected_metadata_json={},
    )
    db.add(asset)
    await db.commit()

    response = await client.put(
        f"/api/v1/research-assets/{asset.id}/classification",
        json={"classification": "restricted"},
        headers=researcher_headers,
    )

    assert response.status_code == 200
    assert response.json()["classification"] == "restricted"
    assert response.json()["governance_review_status"] == "pending"
    assert "protected_metadata_json" not in response.json()


async def test_owner_downgrade_requires_reason_and_records_change(
    client: AsyncClient,
    researcher_headers: dict,
    researcher_user: User,
    db: AsyncSession,
) -> None:
    asset = ResearchAsset(
        asset_type="uploaded_file",
        title="Owner restricted dataset",
        owner_id=researcher_user.id,
        steward_user_id=researcher_user.id,
        classification="restricted",
        protected_metadata_json={"storage_zone": "secure-a"},
    )
    db.add(asset)
    await db.commit()

    denied = await client.put(
        f"/api/v1/research-assets/{asset.id}/classification",
        json={"classification": "internal"},
        headers=researcher_headers,
    )
    allowed = await client.put(
        f"/api/v1/research-assets/{asset.id}/classification",
        json={
            "classification": "internal",
            "governance_reason": "Approved for laboratory reuse",
        },
        headers=researcher_headers,
    )

    assert denied.status_code == 400
    assert denied.json()["detail"] == "A reason is required to lower classification"
    assert allowed.status_code == 200
    await db.refresh(asset)
    assert asset.protected_metadata_json["storage_zone"] == "secure-a"
    [change] = asset.protected_metadata_json["classification_changes"]
    assert change["from"] == "restricted"
    assert change["to"] == "internal"
    assert change["reason"] == "Approved for laboratory reuse"
    assert change["changed_by"] == researcher_user.id
    assert change["changed_at"]


async def test_classification_endpoint_rejects_unauthorized_member(
    client: AsyncClient,
    researcher_headers: dict,
    admin_user: User,
    db: AsyncSession,
) -> None:
    asset = ResearchAsset(
        asset_type="uploaded_file",
        title="Admin dataset",
        owner_id=admin_user.id,
        steward_user_id=admin_user.id,
        classification="internal",
    )
    db.add(asset)
    await db.commit()

    response = await client.put(
        f"/api/v1/research-assets/{asset.id}/classification",
        json={"classification": "confidential"},
        headers=researcher_headers,
    )

    assert response.status_code == 403


async def test_only_owning_group_pi_can_use_classification_endpoint(
    client: AsyncClient,
    pi_headers: dict,
    pi_user: User,
    admin_user: User,
    db: AsyncSession,
) -> None:
    owning_group = ResearchGroup(name="Endpoint Owning Lab", created_by=admin_user.id)
    other_group = ResearchGroup(name="Endpoint Other Lab", created_by=admin_user.id)
    other_pi = User(
        username="other-endpoint-pi",
        hashed_password="not-used-by-token-auth",
        role="pi",
    )
    db.add_all([owning_group, other_group, other_pi])
    await db.flush()
    db.add_all(
        [
            ResearchGroupMember(
                group_id=owning_group.id,
                user_id=pi_user.id,
                role="pi",
                created_by=admin_user.id,
            ),
            ResearchGroupMember(
                group_id=other_group.id,
                user_id=other_pi.id,
                role="pi",
                created_by=admin_user.id,
            ),
        ]
    )
    asset = ResearchAsset(
        asset_type="uploaded_file",
        title="Owning group asset",
        owning_group_id=owning_group.id,
        classification="internal",
    )
    db.add(asset)
    await db.commit()
    other_pi_headers = {
        "Authorization": f"Bearer {create_access_token(other_pi.id)}"
    }

    allowed = await client.put(
        f"/api/v1/research-assets/{asset.id}/classification",
        json={"classification": "confidential"},
        headers=pi_headers,
    )
    denied = await client.put(
        f"/api/v1/research-assets/{asset.id}/classification",
        json={"classification": "restricted"},
        headers=other_pi_headers,
    )

    assert allowed.status_code == 200
    assert denied.status_code == 403


async def test_undiscoverable_top_secret_classification_change_returns_404(
    client: AsyncClient,
    researcher_headers: dict,
    admin_user: User,
    db: AsyncSession,
) -> None:
    asset = ResearchAsset(
        asset_type="uploaded_file",
        title="Hidden top secret asset",
        owner_id=admin_user.id,
        steward_user_id=admin_user.id,
        classification="top_secret",
    )
    db.add(asset)
    await db.commit()

    response = await client.put(
        f"/api/v1/research-assets/{asset.id}/classification",
        json={
            "classification": "restricted",
            "governance_reason": "Approved downgrade",
        },
        headers=researcher_headers,
    )

    assert response.status_code == 404


async def test_classification_endpoint_rejects_unchanged_and_inactive_assets(
    client: AsyncClient,
    auth_headers: dict,
    admin_user: User,
    db: AsyncSession,
) -> None:
    unchanged_asset = ResearchAsset(
        asset_type="uploaded_file",
        title="Unchanged asset",
        owner_id=admin_user.id,
        steward_user_id=admin_user.id,
        classification="internal",
    )
    archived_asset = ResearchAsset(
        asset_type="uploaded_file",
        title="Archived asset",
        owner_id=admin_user.id,
        steward_user_id=admin_user.id,
        classification="internal",
        lifecycle_status="archived",
    )
    db.add_all([unchanged_asset, archived_asset])
    await db.commit()

    unchanged = await client.put(
        f"/api/v1/research-assets/{unchanged_asset.id}/classification",
        json={"classification": "internal"},
        headers=auth_headers,
    )
    inactive = await client.put(
        f"/api/v1/research-assets/{archived_asset.id}/classification",
        json={"classification": "confidential"},
        headers=auth_headers,
    )

    assert unchanged.status_code == 400
    assert inactive.status_code == 409
```

- [ ] **Step 2: Run the endpoint tests and verify RED**

Run:

```bash
OPENCOLAB_DATABASE_URL='sqlite+aiosqlite:///./tmp/settings.db' \
backend/.venv/bin/python -c 'import os, sys, pytest; code=pytest.main([
  "-q",
  "tests/test_research_asset_governance.py",
  "-k", "classification_endpoint or owner_can_raise or owner_downgrade",
  "--tb=short",
]); sys.stdout.flush(); sys.stderr.flush(); os._exit(code)'
```

Expected: failures with HTTP 404 because the dedicated endpoint does not exist.

- [ ] **Step 3: Add the request schema**

In `backend/app/schemas/research_asset.py`, add:

```python
class ResearchAssetClassificationUpdate(BaseModel):
    classification: Literal[
        "public",
        "internal",
        "confidential",
        "restricted",
        "top_secret",
    ]
    governance_reason: str | None = Field(
        default=None,
        max_length=2000,
    )
```

Import the schema from `backend/app/api/research_assets.py`.

- [ ] **Step 4: Add the dedicated endpoint**

Import `UTC` and `datetime` at the top of
`backend/app/api/research_assets.py`:

```python
from datetime import UTC, datetime
```

Add one shared order constant next to `UPLOAD_CLASSIFICATIONS`:

```python
CLASSIFICATION_ORDER = {
    "public": 0,
    "internal": 1,
    "confidential": 2,
    "restricted": 3,
    "top_secret": 4,
}
```

Reuse this constant in the existing governance endpoint instead of its local
dictionary.

Add the endpoint before the general governance endpoint:

```python
@router.put(
    "/research-assets/{asset_id}/classification",
    response_model=ResearchAssetCatalogListResponse,
)
async def update_asset_classification(
    asset_id: str,
    body: ResearchAssetClassificationUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    asset = await _get_asset_or_404(db, asset_id)
    if asset.lifecycle_status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Asset is not active",
        )
    can_change = await can_user_change_classification(db, user, asset)
    if not can_change and not await can_user_discover_asset(db, user, asset):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found",
        )
    if not can_change:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    if body.classification == asset.classification:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Classification is unchanged",
        )

    reason = (body.governance_reason or "").strip()
    lowering = (
        CLASSIFICATION_ORDER[body.classification]
        < CLASSIFICATION_ORDER[asset.classification]
    )
    if lowering and not reason:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A reason is required to lower classification",
        )

    protected_metadata = dict(asset.protected_metadata_json or {})
    changes = list(protected_metadata.get("classification_changes") or [])
    changes.append(
        {
            "from": asset.classification,
            "to": body.classification,
            "reason": reason or None,
            "changed_by": user.id,
            "changed_at": datetime.now(UTC).isoformat(),
        }
    )
    protected_metadata["classification_changes"] = changes
    asset.protected_metadata_json = protected_metadata
    asset.classification = body.classification
    asset.governance_review_status = "pending"
    await db.commit()
    await db.refresh(asset)

    source = await db.get(Source, asset.source_id) if asset.source_id else None
    return await _catalog_response(db, user, asset, source=source)
```

- [ ] **Step 5: Verify GREEN and existing governance behavior**

Run:

```bash
OPENCOLAB_DATABASE_URL='sqlite+aiosqlite:///./tmp/settings.db' \
backend/.venv/bin/python -c 'import os, sys, pytest; code=pytest.main([
  "-q",
  "tests/test_research_asset_governance.py",
  "tests/test_research_assets.py",
  "--tb=short",
]); sys.stdout.flush(); sys.stderr.flush(); os._exit(code)'
```

Expected: all tests in both files pass.

- [ ] **Step 6: Commit the endpoint**

```bash
git add \
  backend/app/schemas/research_asset.py \
  backend/app/api/research_assets.py \
  tests/test_research_asset_governance.py
git commit -m "feat: update asset classification safely"
```

### Task 3: Build the Classification Change Modal

**Files:**
- Create: `frontend/src/components/library/ClassificationChangeModal.tsx`
- Modify: `frontend/src/types/research-asset.ts`
- Modify: `frontend/src/locales/en-US.json`
- Modify: `frontend/src/locales/zh-CN.json`

- [ ] **Step 1: Add the response capability type**

Add to `ResearchAsset` in
`frontend/src/types/research-asset.ts`:

```typescript
can_change_classification: boolean;
```

- [ ] **Step 2: Add localized copy**

Add these keys to `frontend/src/locales/en-US.json`:

```json
"library.classificationChange.action": "Change",
"library.classificationChange.title": "Change Data Classification",
"library.classificationChange.current": "Current classification",
"library.classificationChange.target": "New classification",
"library.classificationChange.reason": "Change reason",
"library.classificationChange.reasonOptional": "Change reason (optional)",
"library.classificationChange.reasonPlaceholder": "Describe why this classification is changing",
"library.classificationChange.loweringWarning": "Lowering classification may expand metadata or content access. A reason is required.",
"library.classificationChange.success": "Data classification updated",
"library.classificationChange.failed": "Failed to update data classification",
"library.classificationChange.unchanged": "Select a different classification"
```

Add the corresponding keys to `frontend/src/locales/zh-CN.json`:

```json
"library.classificationChange.action": "修改",
"library.classificationChange.title": "修改数据等级",
"library.classificationChange.current": "当前等级",
"library.classificationChange.target": "目标等级",
"library.classificationChange.reason": "变更原因",
"library.classificationChange.reasonOptional": "变更原因（选填）",
"library.classificationChange.reasonPlaceholder": "请说明修改数据等级的原因",
"library.classificationChange.loweringWarning": "降低数据等级可能扩大元数据或内容访问范围，必须填写变更原因。",
"library.classificationChange.success": "数据等级已更新",
"library.classificationChange.failed": "数据等级更新失败",
"library.classificationChange.unchanged": "请选择不同的数据等级"
```

- [ ] **Step 3: Create the focused modal component**

Create `frontend/src/components/library/ClassificationChangeModal.tsx`:

```tsx
import { Alert, Input, Modal, Select, Space, Typography, message } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import apiClient from '../../services/api-client';
import type { AssetClassification, ResearchAsset } from '../../types/research-asset';
import { ClassificationTag } from './AssetTags';

const CLASSIFICATIONS: AssetClassification[] = [
  'public',
  'internal',
  'confidential',
  'restricted',
  'top_secret',
];

const CLASSIFICATION_ORDER: Record<AssetClassification, number> = {
  public: 0,
  internal: 1,
  confidential: 2,
  restricted: 3,
  top_secret: 4,
};

interface ClassificationChangeModalProps {
  asset: ResearchAsset;
  open: boolean;
  onCancel: () => void;
  onSuccess: (asset: ResearchAsset) => void;
}

export default function ClassificationChangeModal({
  asset,
  open,
  onCancel,
  onSuccess,
}: ClassificationChangeModalProps) {
  const { t } = useTranslation();
  const [target, setTarget] = useState<AssetClassification>(asset.classification);
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open) {
      setTarget(asset.classification);
      setReason('');
    }
  }, [asset.classification, open]);

  const lowering = useMemo(
    () => CLASSIFICATION_ORDER[target] < CLASSIFICATION_ORDER[asset.classification],
    [asset.classification, target],
  );
  const unchanged = target === asset.classification;
  const confirmDisabled = unchanged || (lowering && !reason.trim());

  const submit = async () => {
    if (confirmDisabled || submitting) return;
    setSubmitting(true);
    try {
      const { data } = await apiClient.put<Partial<ResearchAsset>>(
        `/research-assets/${asset.id}/classification`,
        {
          classification: target,
          governance_reason: reason.trim() || null,
        },
      );
      message.success(t('library.classificationChange.success'));
      onSuccess({ ...asset, ...data });
    } catch (error: unknown) {
      const detail = (
        error as { response?: { data?: { detail?: string } } }
      )?.response?.data?.detail;
      message.error(detail || t('library.classificationChange.failed'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      title={t('library.classificationChange.title')}
      open={open}
      onCancel={onCancel}
      onOk={() => void submit()}
      confirmLoading={submitting}
      okButtonProps={{ disabled: confirmDisabled }}
      destroyOnHidden
    >
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <Space>
          <Typography.Text type="secondary">
            {t('library.classificationChange.current')}
          </Typography.Text>
          <ClassificationTag value={asset.classification} />
        </Space>
        <Select
          aria-label={t('library.classificationChange.target')}
          value={target}
          onChange={(value) => setTarget(value as AssetClassification)}
          style={{ width: '100%' }}
          options={CLASSIFICATIONS.map((classification) => ({
            value: classification,
            label: t(`library.classification.${classification}`),
          }))}
        />
        {lowering ? (
          <Alert
            type="warning"
            showIcon
            message={t('library.classificationChange.loweringWarning')}
          />
        ) : null}
        <div>
          <Typography.Text>
            {t(
              lowering
                ? 'library.classificationChange.reason'
                : 'library.classificationChange.reasonOptional',
            )}
          </Typography.Text>
          <Input.TextArea
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder={t('library.classificationChange.reasonPlaceholder')}
            maxLength={2000}
            autoSize={{ minRows: 3, maxRows: 6 }}
            style={{ marginTop: 8 }}
          />
        </div>
        {unchanged ? (
          <Typography.Text type="secondary">
            {t('library.classificationChange.unchanged')}
          </Typography.Text>
        ) : null}
      </Space>
    </Modal>
  );
}
```

- [ ] **Step 4: Run the frontend build**

Run:

```bash
npm run build --prefix frontend
```

Expected: TypeScript and Vite build succeed. The existing large-chunk warning is
acceptable; type errors are not.

- [ ] **Step 5: Commit the modal**

```bash
git add \
  frontend/src/components/library/ClassificationChangeModal.tsx \
  frontend/src/types/research-asset.ts \
  frontend/src/locales/en-US.json \
  frontend/src/locales/zh-CN.json
git commit -m "feat: add classification change modal"
```

### Task 4: Integrate the Modal Into Asset Details

**Files:**
- Modify: `frontend/src/components/library/AssetDetailDrawer.tsx`
- Modify: `frontend/src/pages/Library.tsx`
- Modify: `frontend/src/pages/ProjectAssets.tsx`

- [ ] **Step 1: Add the drawer callback and trigger**

In `AssetDetailDrawer.tsx`, import `ClassificationChangeModal` and add:

```typescript
onAssetUpdated?: (asset: ResearchAsset) => void;
```

to `AssetDetailDrawerProps`.

Add local state:

```typescript
const [classificationModalOpen, setClassificationModalOpen] = useState(false);
```

Replace the classification description value with:

```tsx
<Space size={4}>
  <ClassificationTag value={asset.classification} />
  {asset.can_change_classification ? (
    <Button
      type="link"
      size="small"
      onClick={() => setClassificationModalOpen(true)}
    >
      {t('library.classificationChange.action')}
    </Button>
  ) : null}
</Space>
```

Render the modal next to the other detail modals:

```tsx
<ClassificationChangeModal
  asset={asset}
  open={classificationModalOpen}
  onCancel={() => setClassificationModalOpen(false)}
  onSuccess={(updatedAsset) => {
    setClassificationModalOpen(false);
    onAssetUpdated?.(updatedAsset);
  }}
/>
```

Destructure `onAssetUpdated` from the component props.

- [ ] **Step 2: Refresh laboratory list state after success**

In `Library.tsx`, add:

```typescript
const handleAssetUpdated = (updatedAsset: ResearchAsset) => {
  setDetailAsset(updatedAsset);
  loadAssets();
};
```

Pass it to the drawer:

```tsx
<AssetDetailDrawer
  asset={detailAsset}
  projects={projects}
  onAssetUpdated={handleAssetUpdated}
  extraActions={...}
  onClose={() => setDetailAsset(null)}
/>
```

- [ ] **Step 3: Refresh project list state after success**

In `ProjectAssets.tsx`, add:

```typescript
const handleAssetUpdated = (updatedAsset: ResearchAsset) => {
  setDetailAsset(updatedAsset);
  loadAssets();
};
```

Pass it to the drawer:

```tsx
<AssetDetailDrawer
  asset={detailAsset}
  projects={projects}
  onAssetUpdated={handleAssetUpdated}
  onClose={() => setDetailAsset(null)}
/>
```

- [ ] **Step 4: Build and inspect the focused diff**

Run:

```bash
npm run build --prefix frontend
git diff --check
git diff --stat
```

Expected: build succeeds, `git diff --check` has no output, and the diff contains
only the planned frontend integration files.

- [ ] **Step 5: Commit the integration**

```bash
git add \
  frontend/src/components/library/AssetDetailDrawer.tsx \
  frontend/src/pages/Library.tsx \
  frontend/src/pages/ProjectAssets.tsx
git commit -m "feat: edit classification from asset details"
```

### Task 5: Verify Authorization, UI, and Regression Safety

**Files:**
- Test: `tests/test_research_asset_governance.py`
- Test: `tests/test_research_assets.py`
- Verify: all modified backend and frontend files

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
OPENCOLAB_DATABASE_URL='sqlite+aiosqlite:///./tmp/settings.db' \
backend/.venv/bin/python -c 'import os, sys, pytest; code=pytest.main([
  "-q",
  "tests/test_research_asset_governance.py",
  "tests/test_research_assets.py",
  "--tb=short",
]); sys.stdout.flush(); sys.stderr.flush(); os._exit(code)'
```

Expected: all focused tests pass.

- [ ] **Step 2: Run the full backend suite**

Run:

```bash
OPENCOLAB_DATABASE_URL='sqlite+aiosqlite:///./tmp/settings.db' \
backend/.venv/bin/python -c 'import os, sys, pytest; code=pytest.main([
  "-q", "--tb=short",
]); sys.stdout.flush(); sys.stderr.flush(); os._exit(code)'
```

Expected: all tests pass with zero failures.

- [ ] **Step 3: Run production frontend verification**

Run:

```bash
npm run build --prefix frontend
```

Expected: TypeScript and Vite build succeed.

- [ ] **Step 4: Run repository checks**

Run:

```bash
git diff --check
pre-commit run --all-files
git status --short
```

Expected: no whitespace errors; pre-commit exits 0; only the user's existing
untracked `models/` directory may remain.

- [ ] **Step 5: Verify the live laboratory UI**

At `http://localhost:8430/library`, verify with an eligible owner account:

1. open an existing asset detail drawer;
2. confirm the **Change** action is visible next to Data Classification;
3. select a higher classification and confirm without a reason;
4. verify the drawer and list show the new classification;
5. reopen the modal and select a lower classification;
6. confirm the warning appears and Confirm is disabled while the reason is blank;
7. enter a reason, submit, and verify the drawer and list refresh;
8. confirm a non-owner ordinary member sees no Change action;
9. confirm an owning-group PI sees the action;
10. confirm a PI from another group sees no action.

Expected: UI behavior matches the permission and transition rules, and no
protected metadata or source ID appears in the classification response.

- [ ] **Step 6: Inspect final commits**

Run:

```bash
git log --oneline -6
git status --short
```

Expected: the authority, endpoint, modal, and drawer integration commits are
present on `lab-library`; no feature files are uncommitted.
