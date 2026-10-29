# Upload-Time Research Asset Classification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let every library uploader choose an explicit research data classification, persist it for regular and ZIP uploads, and display it in the library UI.

**Architecture:** Keep legacy visibility and governance classification as separate multipart fields. The upload endpoint validates classification before processing the file, materializes assets through the existing service, then applies the selected classification to every resulting asset before publication. The frontend adds a classification selector and reuses a dedicated classification tag in the table and detail drawer.

**Tech Stack:** FastAPI multipart forms, SQLAlchemy async ORM, pytest/httpx, React 19, TypeScript, Ant Design, i18next.

---

## File Map

- Modify `backend/app/api/research_assets.py`: validate the multipart classification field and apply it to all uploaded assets.
- Modify `tests/test_research_assets.py`: cover defaults, explicit classifications, invalid input, and ZIP-wide assignment.
- Modify `frontend/src/pages/Library.tsx`: add upload classification state, submit it, and render a table column.
- Modify `frontend/src/components/library/AssetTags.tsx`: add the shared classification tag.
- Modify `frontend/src/components/library/AssetDetailDrawer.tsx`: show classification in authorized details.
- Modify `frontend/src/types/research-asset.ts`: type the five classification values.
- Modify `frontend/src/locales/en-US.json`: add English upload and classification labels.
- Modify `frontend/src/locales/zh-CN.json`: add Simplified Chinese upload and classification labels.

### Task 1: Validate and Persist Classification for All Uploads

**Files:**
- Modify: `tests/test_research_assets.py`
- Modify: `backend/app/api/research_assets.py`

- [ ] **Step 1: Write failing tests before changing production code**

Add imports:

```python
import io
import zipfile
```

Extend the existing upload test and add explicit, invalid, and ZIP tests:

```python
async def test_upload_library_asset_creates_public_asset(
    client: AsyncClient,
    auth_headers,
):
    response = await client.post(
        "/api/v1/library/assets/upload",
        data={"visibility_scope": "lab_public"},
        files={"file": ("library.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
        headers=auth_headers,
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload[0]["classification"] == "internal"


async def test_upload_library_asset_applies_explicit_classification(
    client: AsyncClient,
    auth_headers,
):
    response = await client.post(
        "/api/v1/library/assets/upload",
        data={
            "visibility_scope": "lab_private",
            "classification": "confidential",
        },
        files={
            "file": (
                "confidential.csv",
                b"sample,value\nA,1\n",
                "text/csv",
            )
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    assert response.json()[0]["classification"] == "confidential"


async def test_upload_library_asset_rejects_invalid_classification(
    client: AsyncClient,
    auth_headers,
):
    response = await client.post(
        "/api/v1/library/assets/upload",
        data={
            "visibility_scope": "lab_public",
            "classification": "secret-ish",
        },
        files={"file": ("invalid.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid classification"


async def test_zip_upload_applies_classification_to_every_asset(
    client: AsyncClient,
    auth_headers,
):
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("experiment-a.pdf", b"%PDF-1.4\n%%EOF")
        bundle.writestr("experiment-b.csv", b"sample,value\nB,2\n")

    response = await client.post(
        "/api/v1/library/assets/upload",
        data={
            "visibility_scope": "lab_private",
            "classification": "restricted",
        },
        files={
            "file": (
                "restricted-bundle.zip",
                archive.getvalue(),
                "application/zip",
            )
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload
    assert {asset["classification"] for asset in payload} == {"restricted"}
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
OPENCOLAB_DATABASE_URL='sqlite+aiosqlite:///./tmp/settings.db' \
backend/.venv/bin/python -m pytest \
tests/test_research_assets.py::test_upload_library_asset_creates_public_asset \
tests/test_research_assets.py::test_upload_library_asset_applies_explicit_classification \
tests/test_research_assets.py::test_upload_library_asset_rejects_invalid_classification \
tests/test_research_assets.py::test_zip_upload_applies_classification_to_every_asset \
-q
```

Expected: the default assertion passes. The explicit and ZIP assertions fail
because assets remain `internal`, and invalid classification fails because the
endpoint returns 201 instead of 400.

- [ ] **Step 3: Add server-side form validation and assignment**

In `backend/app/api/research_assets.py`, import `AssetClassification`, define the accepted values once, accept the form field, and assign it before publication:

```python
from app.core.governance import AssetClassification

UPLOAD_CLASSIFICATIONS = {item.value for item in AssetClassification}


async def upload_library_asset(
    file: UploadFile,
    visibility_scope: str = Form("lab_public"),
    classification: str = Form(AssetClassification.INTERNAL),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if visibility_scope not in {"lab_private", "lab_public"}:
        raise HTTPException(status_code=400, detail="Invalid visibility_scope")
    if classification not in UPLOAD_CLASSIFICATIONS:
        raise HTTPException(status_code=400, detail="Invalid classification")
```

In the existing publication loop, add the assignment immediately before
`publish_asset`:

```python
    for asset in assets:
        asset.classification = classification
        await publish_asset(
            db=db,
            asset=asset,
            user=user,
            visibility_scope=visibility_scope,
            description=None,
            publication_note="uploaded from lab library",
        )
```

- [ ] **Step 4: Run the tests and verify GREEN**

Run:

```bash
OPENCOLAB_DATABASE_URL='sqlite+aiosqlite:///./tmp/settings.db' \
backend/.venv/bin/python -c \
'import os, pytest; code=pytest.main(["tests/test_research_assets.py::test_upload_library_asset_creates_public_asset","tests/test_research_assets.py::test_upload_library_asset_applies_explicit_classification","tests/test_research_assets.py::test_upload_library_asset_rejects_invalid_classification","tests/test_research_assets.py::test_zip_upload_applies_classification_to_every_asset","-q"]); os._exit(code)'
```

Expected: `4 passed`.

- [ ] **Step 5: Run the complete asset API test file**

```bash
OPENCOLAB_DATABASE_URL='sqlite+aiosqlite:///./tmp/settings.db' \
backend/.venv/bin/python -c \
'import os, sys, pytest; code=pytest.main(["tests/test_research_assets.py","-q","--tb=short"]); sys.stdout.flush(); sys.stderr.flush(); os._exit(code)'
```

Expected: all tests in `tests/test_research_assets.py` pass.

- [ ] **Step 6: Commit backend behavior and coverage**

```bash
git add backend/app/api/research_assets.py tests/test_research_assets.py
git commit -m "feat: classify library uploads"
```

### Task 2: Add Classification Selection and Display to the Library UI

**Files:**
- Modify: `frontend/src/pages/Library.tsx`
- Modify: `frontend/src/components/library/AssetTags.tsx`
- Modify: `frontend/src/components/library/AssetDetailDrawer.tsx`
- Modify: `frontend/src/types/research-asset.ts`
- Modify: `frontend/src/locales/en-US.json`
- Modify: `frontend/src/locales/zh-CN.json`

- [ ] **Step 1: Add the explicit TypeScript classification type**

In `frontend/src/types/research-asset.ts`:

```typescript
export type AssetClassification =
  | 'public'
  | 'internal'
  | 'confidential'
  | 'restricted'
  | 'top_secret';

export interface ResearchAsset {
  classification: AssetClassification;
}
```

- [ ] **Step 2: Add a reusable classification tag**

In `frontend/src/components/library/AssetTags.tsx`:

```tsx
const classificationColor: Record<string, string> = {
  public: 'green',
  internal: 'blue',
  confidential: 'gold',
  restricted: 'orange',
  top_secret: 'red',
};

export function ClassificationTag({ value }: { value: string }) {
  const { t } = useTranslation();
  return (
    <Tag color={classificationColor[value] || 'default'}>
      {t(`library.classification.${value}`, value)}
    </Tag>
  );
}
```

- [ ] **Step 3: Submit the selected classification**

In `frontend/src/pages/Library.tsx`, import `AssetClassification`, add state,
append it to the multipart body, and add the selector beside visibility:

```tsx
import type {
  AssetClassification,
  ResearchAsset,
} from '../types/research-asset';

const CLASSIFICATION_OPTIONS: AssetClassification[] = [
  'public',
  'internal',
  'confidential',
  'restricted',
  'top_secret',
];

const [uploadClassification, setUploadClassification] =
  useState<AssetClassification>('internal');

formData.append('classification', uploadClassification);

<Select
  aria-label={t('library.classification')}
  value={uploadClassification}
  onChange={setUploadClassification}
  style={{ width: 160 }}
  options={CLASSIFICATION_OPTIONS.map((classification) => ({
    value: classification,
    label: t(`library.classification.${classification}`),
  }))}
/>
```

- [ ] **Step 4: Show classification in the list and detail drawer**

Import `ClassificationTag` in both components. Add a table column in
`Library.tsx`:

```tsx
{
  title: t('library.classification'),
  dataIndex: 'classification',
  width: 140,
  render: (value: string) => <ClassificationTag value={value} />,
},
```

Add a detail row in `AssetDetailDrawer.tsx` after visibility:

```tsx
<Descriptions.Item label={t('library.detail.classification')}>
  <ClassificationTag value={asset.classification} />
</Descriptions.Item>
```

- [ ] **Step 5: Add English and Chinese translations**

Add equivalent keys to both locale files.

`frontend/src/locales/en-US.json`:

```json
"library.classification": "Data Classification",
"library.classification.public": "Public",
"library.classification.internal": "Internal",
"library.classification.confidential": "Confidential",
"library.classification.restricted": "Restricted",
"library.classification.top_secret": "Top Secret",
"library.detail.classification": "Data Classification"
```

`frontend/src/locales/zh-CN.json`:

```json
"library.classification": "数据等级",
"library.classification.public": "公开",
"library.classification.internal": "内部",
"library.classification.confidential": "保密",
"library.classification.restricted": "限制访问",
"library.classification.top_secret": "核心机密",
"library.detail.classification": "数据等级"
```

- [ ] **Step 6: Run the frontend production build**

If the worktree does not contain dependencies, temporarily link the existing
workspace dependencies:

```bash
ln -s frontend/node_modules frontend/node_modules
npm run build --prefix frontend
unlink frontend/node_modules
```

Expected: TypeScript and Vite build succeed. The existing bundle-size warning is
acceptable.

- [ ] **Step 7: Commit the UI**

```bash
git add \
  frontend/src/pages/Library.tsx \
  frontend/src/components/library/AssetTags.tsx \
  frontend/src/components/library/AssetDetailDrawer.tsx \
  frontend/src/types/research-asset.ts \
  frontend/src/locales/en-US.json \
  frontend/src/locales/zh-CN.json
git commit -m "feat: select upload data classification"
```

### Task 3: Final Verification

**Files:**
- Verify all files changed in Tasks 1–3.

- [ ] **Step 1: Run backend full tests**

```bash
OPENCOLAB_DATABASE_URL='sqlite+aiosqlite:///./tmp/settings.db' \
backend/.venv/bin/python -c \
'import os, sys, pytest; code=pytest.main(["-q","--tb=short"]); sys.stdout.flush(); sys.stderr.flush(); os._exit(code)'
```

Expected: all backend tests pass with zero failures.

- [ ] **Step 2: Run frontend production build again**

```bash
ln -s frontend/node_modules frontend/node_modules
npm run build --prefix frontend
unlink frontend/node_modules
```

Expected: build succeeds; the known bundle-size warning may remain.

- [ ] **Step 3: Run repository checks**

```bash
git diff --check
pre-commit run --all-files
git status --short
```

Expected: no diff errors, pre-commit exits successfully, and only intentional
changes are present.

- [ ] **Step 4: Manual acceptance checks**

1. Open `/library`.
2. Confirm Visibility and Data Classification are separate selects.
3. Upload a file with Confidential and confirm the list and detail show
   Confidential.
4. Upload a file with Restricted and confirm the list and detail show
   Restricted.
5. Confirm an unauthorized user can discover only metadata allowed by the
   existing policy evaluator and cannot preview content.

- [ ] **Step 5: Record final branch state**

```bash
git log -5 --oneline
git status --short
```

Expected: implementation commits are present and the worktree is clean.
