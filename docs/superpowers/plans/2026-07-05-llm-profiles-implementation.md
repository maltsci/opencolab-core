# LLM Profiles Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the duplicated `LLM API Keys + System Settings` admin flow with `LLM Profiles + Active Profile`, add model fetching and model health testing, and keep runtime compatibility with existing OpenColab deployments.

**Architecture:** Add a first-class `LLMProfile` backend model and migrate existing `LLMKey` records into it. Narrow runtime config to `active_llm_profile_id` plus `llm_model_override`, then update the admin frontend so profiles own connection details and selected model while settings only choose the active profile and optional advanced model override.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Pydantic v2, React, Vite, Ant Design, React i18next, pytest

---

## File Structure

### Backend

- Create: `backend/app/models/llm_profile.py`
  - New persistent profile model with provider, endpoint, encrypted key, selected model, status, and test metadata.
- Create: `backend/app/schemas/llm_profile.py`
  - Profile CRUD, fetch-models, test-connection, and test-model request/response schemas.
- Create: `backend/app/services/llm_profile_service.py`
  - Shared logic for listing models, testing connections, testing completion probes, and activation helpers.
- Create: `backend/alembic/versions/<timestamp>_add_llm_profiles.py`
  - Schema migration and data migration from `llm_keys` to `llm_profiles`.
- Modify: `backend/app/api/admin.py`
  - Add `/admin/llm-profiles*` endpoints and narrow config updates to `active_llm_profile_id` and `llm_model_override`.
- Modify: `backend/app/services/runtime_config.py`
  - Resolve runtime values from active profile first, keep legacy fallback support.
- Modify: `backend/app/services/llm_key_service.py`
  - Extract reusable provider probing helpers or retire the file into profile service usage.
- Modify: `backend/app/models/__init__` equivalents if present through import sites.
- Modify: `backend/app/api/websocket.py`
  - Keep runtime resolution aligned with active profile and model override.

### Frontend

- Modify: `frontend/src/pages/admin/LLMKeys.tsx`
  - Convert page into `LLM Profiles` list with status, model column, test, set active, edit, delete.
- Modify: `frontend/src/pages/admin/Settings.tsx`
  - Reduce LLM section to active profile selector and collapsible model override.
- Modify: `frontend/src/App.tsx`
  - Rename admin route label from `LLM API Keys` to `LLM Profiles`.
- Modify: `frontend/src/locales/en-US.json`
- Modify: `frontend/src/locales/zh-CN.json`
  - Add profile-oriented copy, statuses, actions, and advanced section text.

### Tests

- Modify: `tests/test_admin.py`
  - Cover profile CRUD, activation, fetch-models, test-connection, test-model, and config shape.
- Create: `tests/test_llm_profile_service.py`
  - Service-level tests for model discovery and completion health probe behavior.
- Modify: `tests/test_llm_service.py`
  - Ensure runtime resolution honors active profile and model override.

---

### Task 1: Add the LLMProfile backend model and migration

**Files:**
- Create: `backend/app/models/llm_profile.py`
- Create: `backend/alembic/versions/<timestamp>_add_llm_profiles.py`
- Modify: `backend/app/models/llm_key.py`
- Test: `tests/test_admin.py`

- [ ] **Step 1: Write the failing migration-oriented test**

```python
async def test_profile_list_starts_from_migrated_legacy_key(
    client: AsyncClient,
    auth_headers,
    db,
):
    legacy = LLMKey(
        provider="openai",
        name="Legacy GLM",
        api_base="https://llm-api.healwrap.cn/v1/",
        encrypted_key=encrypt_api_key("sk-legacy"),
    )
    db.add(legacy)
    db.add(SystemConfig(key="llm_model", value="openai/glm-5"))
    db.add(SystemConfig(key="llm_key_id", value=legacy.id))
    await db.commit()

    response = await client.get("/api/v1/admin/llm-profiles", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()[0]["name"] == "Legacy GLM"
    assert response.json()[0]["model"] == "openai/glm-5"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=backend backend/.venv/bin/pytest tests/test_admin.py::test_profile_list_starts_from_migrated_legacy_key -v`

Expected: FAIL with `404` or missing `/api/v1/admin/llm-profiles` route.

- [ ] **Step 3: Add the new SQLAlchemy model**

```python
class LLMProfile(Base):
    __tablename__ = "llm_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(200))
    provider: Mapped[str] = mapped_column(String(50))
    api_base: Mapped[str | None] = mapped_column(String(500), nullable=True)
    encrypted_key: Mapped[str] = mapped_column(String(500))
    model: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(50), default="unknown")
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_test_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

- [ ] **Step 4: Add the Alembic migration**

```python
def upgrade() -> None:
    op.create_table(
        "llm_profiles",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("api_base", sa.String(length=500), nullable=True),
        sa.Column("encrypted_key", sa.String(length=500), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False, server_default="gpt-4o-mini"),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="unknown"),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_result", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.add_column("system_configs", sa.Column("key", sa.String(length=255), nullable=False, existing_type=sa.String(length=255)))
```

And in the migration data step:

```python
connection = op.get_bind()
legacy_keys = connection.execute(sa.text("SELECT id, name, provider, api_base, encrypted_key FROM llm_keys")).mappings().all()
runtime_model = connection.execute(
    sa.text("SELECT value FROM system_configs WHERE key = 'llm_model' ORDER BY id LIMIT 1")
).scalar() or "gpt-4o-mini"

for row in legacy_keys:
    connection.execute(
        sa.text(
            """
            INSERT INTO llm_profiles (id, name, provider, api_base, encrypted_key, model, status)
            VALUES (:id, :name, :provider, :api_base, :encrypted_key, :model, 'unknown')
            """
        ),
        {**row, "model": runtime_model},
    )
```

- [ ] **Step 5: Run the focused test and migration checks**

Run: `PYTHONPATH=backend backend/.venv/bin/pytest tests/test_admin.py::test_profile_list_starts_from_migrated_legacy_key -v`

Expected: still FAIL until routes exist, but migration/model import errors should be gone.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/llm_profile.py backend/alembic/versions
git commit -m "feat: add llm profile model and migration"
```

### Task 2: Add profile schemas and admin profile CRUD APIs

**Files:**
- Create: `backend/app/schemas/llm_profile.py`
- Modify: `backend/app/api/admin.py`
- Test: `tests/test_admin.py`

- [ ] **Step 1: Write the failing CRUD tests**

```python
async def test_create_llm_profile_persists_model(
    client: AsyncClient,
    auth_headers,
):
    response = await client.post(
        "/api/v1/admin/llm-profiles",
        json={
            "name": "Healwrap GLM-5",
            "provider": "openai",
            "api_base": "https://llm-api.healwrap.cn/v1/",
            "key": "sk-glm",
            "model": "openai/glm-5",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201

    listing = await client.get("/api/v1/admin/llm-profiles", headers=auth_headers)
    body = listing.json()
    assert body[0]["model"] == "openai/glm-5"
    assert body[0]["status"] == "unknown"
```

```python
async def test_activate_llm_profile_updates_runtime_config(
    client: AsyncClient,
    auth_headers,
    db,
):
    profile = LLMProfile(
        name="Healwrap GLM-5",
        provider="openai",
        api_base="https://llm-api.healwrap.cn/v1/",
        encrypted_key=encrypt_api_key("sk-glm"),
        model="openai/glm-5",
    )
    db.add(profile)
    await db.commit()

    response = await client.post(f"/api/v1/admin/llm-profiles/{profile.id}/activate", headers=auth_headers)
    assert response.status_code == 200

    config = await client.get("/api/v1/admin/config", headers=auth_headers)
    assert config.json()["active_llm_profile_id"] == profile.id
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=backend backend/.venv/bin/pytest tests/test_admin.py::test_create_llm_profile_persists_model tests/test_admin.py::test_activate_llm_profile_updates_runtime_config -v`

Expected: FAIL with missing route or missing schema fields.

- [ ] **Step 3: Add profile request and response schemas**

```python
class LLMProfileCreate(BaseModel):
    name: str
    provider: str
    api_base: str | None = None
    key: str
    model: str


class LLMProfileUpdate(BaseModel):
    name: str
    provider: str
    api_base: str | None = None
    key: str | None = None
    model: str


class LLMProfileResponse(BaseModel):
    id: str
    name: str
    provider: str
    api_base: str | None
    model: str
    status: str
    last_tested_at: datetime | None
    last_test_result: str | None
    masked_key: str
```

- [ ] **Step 4: Add admin CRUD and activate endpoints**

```python
@router.get("/llm-profiles", response_model=list[LLMProfileResponse])
async def list_llm_profiles(...):
    ...


@router.post("/llm-profiles", status_code=status.HTTP_201_CREATED)
async def create_llm_profile(...):
    ...


@router.put("/llm-profiles/{profile_id}")
async def update_llm_profile(...):
    ...


@router.delete("/llm-profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_llm_profile(...):
    ...


@router.post("/llm-profiles/{profile_id}/activate")
async def activate_llm_profile(...):
    await set_runtime_values({"active_llm_profile_id": profile_id}, db)
    return {"status": "ok"}
```

- [ ] **Step 5: Run the focused CRUD tests**

Run: `PYTHONPATH=backend backend/.venv/bin/pytest tests/test_admin.py::test_create_llm_profile_persists_model tests/test_admin.py::test_activate_llm_profile_updates_runtime_config -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/admin.py backend/app/schemas/llm_profile.py tests/test_admin.py
git commit -m "feat: add llm profile admin apis"
```

### Task 3: Implement profile probing service for fetch-models, connection test, and model test

**Files:**
- Create: `backend/app/services/llm_profile_service.py`
- Modify: `backend/app/api/admin.py`
- Test: `tests/test_llm_profile_service.py`
- Test: `tests/test_admin.py`

- [ ] **Step 1: Write the failing service tests**

```python
@pytest.mark.asyncio
async def test_fetch_models_returns_sorted_model_ids(monkeypatch):
    async def fake_list_models(*args, **kwargs):
        return ["glm-5", "kimi-k2.5"]

    monkeypatch.setattr(llm_profile_service, "_list_models_for_provider", fake_list_models)

    result = await llm_profile_service.fetch_models(
        provider="openai",
        api_base="https://llm-api.healwrap.cn/v1/",
        api_key="sk-test",
    )

    assert result == ["glm-5", "kimi-k2.5"]
```

```python
@pytest.mark.asyncio
async def test_test_model_marks_profile_unhealthy_on_completion_failure(monkeypatch):
    async def fake_probe(*args, **kwargs):
        raise RuntimeError("ReadTimeout")

    monkeypatch.setattr(llm_profile_service, "_probe_completion", fake_probe)

    result = await llm_profile_service.test_model(
        provider="openai",
        api_base="https://llm-api.healwrap.cn/v1/",
        api_key="sk-test",
        model="openai/glm-5",
    )

    assert result["ok"] is False
    assert result["status"] == "model_unhealthy"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=backend backend/.venv/bin/pytest tests/test_llm_profile_service.py -v`

Expected: FAIL because the new service module does not exist yet.

- [ ] **Step 3: Implement provider probing helpers**

```python
async def fetch_models(provider: str, api_base: str | None, api_key: str) -> list[str]:
    ...


async def test_connection(provider: str, api_base: str | None, api_key: str) -> dict[str, str | bool]:
    models = await fetch_models(provider, api_base, api_key)
    return {
        "ok": True,
        "status": "connection_ok",
        "message": f"Connection successful. {len(models)} model(s) listed.",
        "models": models,
    }


async def test_model(provider: str, api_base: str | None, api_key: str, model: str) -> dict[str, str | bool]:
    try:
        await _probe_completion(provider, api_base, api_key, model)
        return {"ok": True, "status": "model_ready", "message": f"Model '{model}' is ready."}
    except Exception as exc:
        return {"ok": False, "status": "model_unhealthy", "message": f"Completion probe for '{model}' failed: {exc}"}
```

- [ ] **Step 4: Wire admin endpoints for fetch-models and tests**

```python
@router.post("/llm-profiles/fetch-models")
async def fetch_llm_profile_models(body: LLMProfileProbeRequest, _=Depends(admin_dep)):
    return {"models": await fetch_models(body.provider, body.api_base, body.key)}


@router.post("/llm-profiles/test-connection")
async def test_llm_profile_connection(body: LLMProfileProbeRequest, _=Depends(admin_dep)):
    return await test_connection(body.provider, body.api_base, body.key)


@router.post("/llm-profiles/test-model")
async def test_llm_profile_model(body: LLMProfileModelProbeRequest, _=Depends(admin_dep)):
    return await test_model(body.provider, body.api_base, body.key, body.model)
```

- [ ] **Step 5: Run service and admin probe tests**

Run: `PYTHONPATH=backend backend/.venv/bin/pytest tests/test_llm_profile_service.py tests/test_admin.py -q`

Expected: PASS for the new probe paths and old admin behavior still green where unchanged.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/llm_profile_service.py backend/app/api/admin.py tests/test_llm_profile_service.py tests/test_admin.py
git commit -m "feat: add llm profile probing endpoints"
```

### Task 4: Refactor runtime config to use active profile and model override

**Files:**
- Modify: `backend/app/services/runtime_config.py`
- Modify: `backend/app/api/websocket.py`
- Modify: `backend/app/services/llm_service.py`
- Test: `tests/test_llm_service.py`
- Test: `tests/test_admin.py`

- [ ] **Step 1: Write the failing runtime resolution tests**

```python
@pytest.mark.asyncio
async def test_runtime_prefers_active_profile_over_legacy_fields(db):
    profile = LLMProfile(
        name="Healwrap GLM-5",
        provider="openai",
        api_base="https://llm-api.healwrap.cn/v1/",
        encrypted_key=encrypt_api_key("sk-glm"),
        model="openai/glm-5",
    )
    db.add(profile)
    db.add(SystemConfig(key="active_llm_profile_id", value=profile.id))
    db.add(SystemConfig(key="llm_model", value="openai/legacy-model"))
    await db.commit()

    assert await get_runtime_value("llm_model", db) == "openai/glm-5"
```

```python
@pytest.mark.asyncio
async def test_runtime_uses_model_override_when_present(db):
    profile = LLMProfile(
        name="Healwrap GLM-5",
        provider="openai",
        api_base="https://llm-api.healwrap.cn/v1/",
        encrypted_key=encrypt_api_key("sk-glm"),
        model="openai/glm-5",
    )
    db.add(profile)
    db.add(SystemConfig(key="active_llm_profile_id", value=profile.id))
    db.add(SystemConfig(key="llm_model_override", value="openai/glm-5-air"))
    await db.commit()

    assert await get_runtime_value("llm_model", db) == "openai/glm-5-air"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=backend backend/.venv/bin/pytest tests/test_admin.py::test_runtime_prefers_active_profile_over_legacy_fields tests/test_admin.py::test_runtime_uses_model_override_when_present -v`

Expected: FAIL because runtime still resolves through `llm_key_id` and `llm_model`.

- [ ] **Step 3: Add new runtime keys and resolution order**

```python
RUNTIME_KEYS = {
    "active_llm_profile_id": ("OPENCOLAB_ACTIVE_LLM_PROFILE_ID", None),
    "llm_model_override": ("OPENCOLAB_LLM_MODEL_OVERRIDE", None),
    ...
}
```

And in `get_runtime_value`:

```python
if key == "llm_model":
    override = await _get_db_or_env_value("llm_model_override", db)
    if override:
        return override
    profile = await get_active_llm_profile(db)
    if profile is not None:
        return profile.model
```

And in `get_runtime_llm_api_key`:

```python
profile = await get_active_llm_profile(db)
if profile is not None:
    return decrypt_api_key(profile.encrypted_key)
```

- [ ] **Step 4: Update WebSocket and LLM entry points to read the new runtime values**

```python
llm_model = await get_runtime_value("llm_model", db)
llm_api_base = await get_runtime_value("llm_api_base", db)
llm_api_key = await get_runtime_llm_api_key(db)
```

Keep this call shape but let runtime config resolve through active profile first.

- [ ] **Step 5: Run runtime tests**

Run: `PYTHONPATH=backend backend/.venv/bin/pytest tests/test_llm_service.py tests/test_admin.py -q`

Expected: PASS, including previous timeout and proxy bypass coverage.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/runtime_config.py backend/app/api/websocket.py backend/app/services/llm_service.py tests/test_llm_service.py tests/test_admin.py
git commit -m "refactor: resolve llm runtime from active profile"
```

### Task 5: Redesign the settings page around active profile plus model override

**Files:**
- Modify: `frontend/src/pages/admin/Settings.tsx`
- Modify: `frontend/src/locales/en-US.json`
- Modify: `frontend/src/locales/zh-CN.json`
- Test manually in browser

- [ ] **Step 1: Write the UI expectations as a checklist**

```text
- The LLM section shows Active Profile as the only default selection field.
- The duplicated API Base URL and API Key inputs are removed from the default section.
- A collapsible Advanced section contains only Model Override.
- Saving settings writes active_llm_profile_id and llm_model_override.
```

- [ ] **Step 2: Replace the current settings form shape**

```tsx
interface ConfigValues {
  active_llm_profile_id: string | null;
  llm_model_override: string | null;
  embedding_model: string | null;
  upload_dir: string | null;
  max_file_size_mb: string | null;
  chunk_size: string | null;
  chunk_overlap: string | null;
  rag_top_k: string | null;
}
```

- [ ] **Step 3: Implement the simplified LLM card**

```tsx
<Card title={t('admin.llmConfig')} style={{ marginBottom: 24 }}>
  <Form.Item
    name="active_llm_profile_id"
    label={t('admin.activeLlmProfile')}
    tooltip={t('admin.activeLlmProfileHint')}
  >
    <Select
      allowClear
      placeholder={t('admin.activeLlmProfilePlaceholder')}
      options={profiles.map((profile) => ({
        value: profile.id,
        label: `${profile.name} · ${profile.model}`,
      }))}
    />
  </Form.Item>

  <Collapse ghost items={[{
    key: 'advanced',
    label: t('admin.advancedLlmSettings'),
    children: (
      <Form.Item
        name="llm_model_override"
        label={t('admin.llmModelOverride')}
        tooltip={t('admin.llmModelOverrideHint')}
      >
        <Input placeholder="openai/glm-5" />
      </Form.Item>
    ),
  }]} />
</Card>
```

- [ ] **Step 4: Add locale strings**

```json
"admin.activeLlmProfile": "Active LLM Profile",
"admin.activeLlmProfileHint": "The default model profile used by the system.",
"admin.activeLlmProfilePlaceholder": "Select an active LLM profile",
"admin.advancedLlmSettings": "Advanced",
"admin.llmModelOverride": "Model Override",
"admin.llmModelOverrideHint": "Optional temporary override for debugging."
```

- [ ] **Step 5: Run the frontend build**

Run: `cd frontend && npm run build`

Expected: successful Vite build with no TypeScript errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/admin/Settings.tsx frontend/src/locales/en-US.json frontend/src/locales/zh-CN.json
git commit -m "feat: simplify llm settings around active profile"
```

### Task 6: Convert the LLM Keys page into an LLM Profiles workspace

**Files:**
- Modify: `frontend/src/pages/admin/LLMKeys.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/locales/en-US.json`
- Modify: `frontend/src/locales/zh-CN.json`
- Test manually in browser

- [ ] **Step 1: Write the UI expectations as a checklist**

```text
- The page title reads LLM Profiles.
- The table shows Name, Provider, Model, API Base, Status, Last Tested.
- Actions include Test, Set Active, Edit, Delete.
- Create/Edit modal includes Fetch Models and Test Model.
- Manual model input is available only in Advanced.
```

- [ ] **Step 2: Expand the profile page data types**

```tsx
interface LLMProfile {
  id: string;
  provider: string;
  name: string;
  api_base?: string | null;
  model: string;
  status: string;
  last_tested_at?: string | null;
  last_test_result?: string | null;
  masked_key: string;
}
```

- [ ] **Step 3: Implement the table with active and health actions**

```tsx
{
  title: t('admin.profileStatus'),
  dataIndex: 'status',
  render: (status: string) => <Tag color={statusToColor(status)}>{t(`admin.profileStatus.${status}`)}</Tag>,
},
{
  title: t('common.actions'),
  render: (_, record) => (
    <Space size={8}>
      <Button size="small" onClick={() => testProfile(record)}>{t('admin.testModel')}</Button>
      <Button size="small" type="primary" onClick={() => activateProfile(record.id)}>{t('admin.setActive')}</Button>
      <Button icon={<EditOutlined />} size="small" onClick={() => openEdit(record)} />
      <Popconfirm title={t('common.confirm')} onConfirm={() => deleteProfile(record.id)}>
        <Button icon={<DeleteOutlined />} danger size="small" />
      </Popconfirm>
    </Space>
  ),
}
```

- [ ] **Step 4: Implement fetch-models and advanced manual model input in the modal**

```tsx
<Form.Item label={t('admin.availableModels')} name="model">
  <Select
    showSearch
    options={availableModels.map((model) => ({ value: model, label: model }))}
    placeholder={t('admin.availableModelsPlaceholder')}
  />
</Form.Item>

<Button onClick={handleFetchModels} loading={fetchingModels}>
  {t('admin.fetchModels')}
</Button>

<Collapse ghost items={[{
  key: 'advanced-model',
  label: t('admin.advancedModelEntry'),
  children: (
    <Form.Item name="manual_model" label={t('admin.manualModel')}>
      <Input placeholder="openai/glm-5" />
    </Form.Item>
  ),
}]} />
```

- [ ] **Step 5: Run frontend build and manual browser smoke test**

Run: `cd frontend && npm run build`

Expected: PASS

Then manually verify in the browser:

```text
1. Create a profile
2. Fetch models
3. Select glm-5
4. Test model
5. Set active
6. Confirm Settings page reflects the active profile
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/admin/LLMKeys.tsx frontend/src/App.tsx frontend/src/locales/en-US.json frontend/src/locales/zh-CN.json
git commit -m "feat: add llm profiles admin workspace"
```

### Task 7: Finish compatibility, copy, and regression coverage

**Files:**
- Modify: `tests/test_admin.py`
- Modify: `tests/test_llm_service.py`
- Modify: `tests/test_websocket_errors.py`
- Modify: `backend/app/services/runtime_config.py`
- Modify: `frontend/src/locales/en-US.json`
- Modify: `frontend/src/locales/zh-CN.json`

- [ ] **Step 1: Add regression tests for profile health states**

```python
async def test_test_model_endpoint_returns_listed_but_unhealthy_message(...):
    ...
    assert response.json()["status"] == "model_unhealthy"
    assert "failed" in response.json()["message"].lower()
```

```python
def test_public_websocket_error_message_explains_bad_gateway():
    ...
    assert "502" in message
```

- [ ] **Step 2: Add setup-status and config compatibility assertions**

```python
async def test_setup_status_complete_when_active_profile_is_selected(...):
    ...
    assert response.json() == {"setup_complete": True}
```

```python
async def test_get_config_returns_active_profile_and_model_override(...):
    ...
    assert body["active_llm_profile_id"] == profile.id
    assert body["llm_model_override"] == "openai/glm-5-air"
```

- [ ] **Step 3: Update runtime setup-complete logic**

```python
if result_for_active_profile is not None:
    return True
```

and keep legacy checks after the new active profile path.

- [ ] **Step 4: Run the relevant backend suite**

Run: `PYTHONPATH=backend backend/.venv/bin/pytest tests/test_admin.py tests/test_llm_service.py tests/test_websocket_errors.py tests/test_worker_startup.py -q`

Expected: PASS

- [ ] **Step 5: Run the frontend build one more time**

Run: `cd frontend && npm run build`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add tests/test_admin.py tests/test_llm_service.py tests/test_websocket_errors.py backend/app/services/runtime_config.py frontend/src/locales/en-US.json frontend/src/locales/zh-CN.json
git commit -m "test: cover llm profiles runtime compatibility"
```

## Self-Review

### Spec coverage

- `LLM Profiles` replaces `LLM API Keys`: covered by Tasks 2, 5, and 6.
- `Active Profile` plus advanced `Model Override`: covered by Tasks 4 and 5.
- `Fetch Models`: covered by Task 3 and Task 6.
- `Test Connection` and `Test Model`: covered by Task 3 and Task 6.
- `Listed but unhealthy` health semantics: covered by Tasks 3 and 7.
- Migration from legacy keys: covered by Task 1 and Task 4.
- Future project-level readiness without implementing it now: preserved by Task 4's runtime shape and Task 1's separate profile model.

### Placeholder scan

- No `TODO`, `TBD`, or "implement later" placeholders remain.
- Every code-touching task includes explicit file paths, code examples, commands, and expected outcomes.

### Type consistency

- Backend terminology consistently uses `LLMProfile`, `active_llm_profile_id`, and `llm_model_override`.
- Frontend terminology consistently uses `LLM Profiles`, `Active Profile`, and `Model Override`.
- Health result names stay aligned with the approved spec: `unknown`, `connection_ok`, `model_ready`, `model_unhealthy`, `auth_failed`, `timeout`, `network_error`.
