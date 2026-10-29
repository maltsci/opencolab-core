# Project-Exclusive Upload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let project and session pages upload project-exclusive materials, with session uploads immediately attached to that session, while keeping existing publication and approval policies intact.

**Architecture:** Keep source ingestion, duplicate detection, parsing, and asset materialization in the existing API modules. Add one project-scoped upload route and change the existing session file-upload branch to materialize a `project` asset before linking its source to the session. The session selector continues to use the existing source-link endpoint, but its discovery query is made strictly project-aware and excludes lab-private assets until the normal approval-and-project-link flow has completed.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic v2, pytest/httpx, React, TypeScript, Ant Design, react-i18next.

---

## File map

- `backend/app/api/research_assets.py` — project asset upload endpoint and the reusable project-origin asset materialization helper.
- `backend/app/api/sources.py` — make session file uploads call that helper and attach the resulting source(s) to the session.
- `backend/app/api/sessions.py` — enforce the three allowed categories for the session linking selector.
- `tests/test_research_assets.py` — API-level tests for project and session uploads, duplicate behavior, and project authorization.
- `tests/test_sessions.py` — session discovery category and private-material exclusion tests.
- `frontend/src/pages/ProjectAssets.tsx` — project upload control, duplicate dialog, and list refresh.
- `frontend/src/pages/Session.tsx` — send file uploads through the project-scoped session flow and refresh session sources after upload/link.
- `frontend/src/locales/en-US.json` and `frontend/src/locales/zh-CN.json` — labels and failure messages used by the new controls.

### Task 1: Define and test the reusable project-upload backend behavior

**Files:**
- Modify: `tests/test_research_assets.py`
- Modify: `backend/app/api/research_assets.py`

- [ ] **Step 1: Add a failing project-upload success test**

  Add the test beside the existing library upload tests. It must create a project owned by `pi_user`, upload a small PDF through the new endpoint, and assert the asset is project-origin and linked to the route project.

  ```python
  async def test_project_asset_upload_creates_project_origin_asset(
      client: AsyncClient, pi_headers, pi_user: User, db: AsyncSession
  ):
      project = Project(name="Upload target", description=None)
      db.add(project)
      await db.flush()
      db.add(ResearcherProject(project_id=project.id, researcher_id=pi_user.id, role="owner"))
      await db.commit()

      response = await client.post(
          f"/api/v1/projects/{project.id}/assets/upload",
          files={"file": ("project-paper.pdf", b"%PDF-1.4 project\n%%EOF", "application/pdf")},
          headers=pi_headers,
      )

      assert response.status_code == 201
      payload = response.json()
      assert len(payload) == 1
      assert payload[0]["visibility_scope"] == "project"
      asset = await db.get(ResearchAsset, payload[0]["id"])
      assert asset is not None
      assert asset.origin_project_id == project.id
      link = await db.scalar(
          select(ProjectAssetLink).where(
              ProjectAssetLink.project_id == project.id,
              ProjectAssetLink.asset_id == asset.id,
          )
      )
      assert link is not None
  ```

- [ ] **Step 2: Add a failing project-membership test**

  ```python
  async def test_project_asset_upload_rejects_user_without_project_access(
      client: AsyncClient, researcher_headers, db: AsyncSession
  ):
      project = Project(name="Restricted upload", description=None)
      db.add(project)
      await db.commit()

      response = await client.post(
          f"/api/v1/projects/{project.id}/assets/upload",
          files={"file": ("restricted.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
          headers=researcher_headers,
      )

      assert response.status_code == 404
  ```

- [ ] **Step 3: Run the two tests to verify the route is absent**

  Run: `backend/.venv/bin/pytest tests/test_research_assets.py -k 'project_asset_upload' -v`

  Expected: both tests fail with `404` because `POST /projects/{project_id}/assets/upload` does not exist.

- [ ] **Step 4: Add a project-origin materialization helper**

  In `backend/app/api/research_assets.py`, directly above `upload_library_asset`, add a helper that only accepts a project already authorized through `_get_readable_project`. It must reuse `_create_source_pending`, `_handle_zip_upload`, `_ensure_workspace_link`, `materialize_source_asset`, and `_response`; it must never call `publish_asset`.

  ```python
  async def _upload_project_assets(
      *,
      file: UploadFile,
      project_id: str,
      origin_session_id: str | None,
      user: User,
      db: AsyncSession,
  ) -> list[ResearchAssetResponse]:
      filename = file.filename or ""
      created_source_ids: set[str] = set()
      duplicate_infos: dict[str, DuplicateUploadInfo] = {}
      if filename.lower().endswith(".zip"):
          upload_result = await _handle_zip_upload(
              await file.read(), db, workspace_id=user.workspace.id, owner_id=user.id
          )
          created_source_ids = upload_result.created_source_ids
          source_ids = [source.id for source in upload_result.sources + upload_result.groups]
          sources = list((await db.scalars(select(Source).where(Source.id.in_(source_ids)))).all())
      else:
          source, needs_processing = await _create_source_pending(file, db, owner_id=user.id)
          if needs_processing:
              created_source_ids.add(source.id)
          else:
              duplicate_info = await build_duplicate_upload_info(db=db, user=user, source=source)
              if not duplicate_info.can_use_existing:
                  raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=duplicate_info.model_dump())
              duplicate_infos[source.id] = duplicate_info
          await _ensure_workspace_link(user.workspace.id, source.id, db)
          sources = [source]

      assets: list[ResearchAsset] = []
      for source in sources:
          asset = await materialize_source_asset(
              db=db,
              source=source,
              owner_id=user.id,
              origin_project_id=project_id,
              origin_session_id=origin_session_id,
              visibility_scope="project",
              link_type="source",
              creation_context=AssetCreationContext(scope="project", owning_group_id=None),
          )
          if source.id in created_source_ids:
              asset.classification = "internal"
          assets.append(asset)

      await db.commit()
      for asset in assets:
          await db.refresh(asset)
      return [
          await _response(db, user, asset, duplicate_info=duplicate_infos.get(asset.source_id or ""))
          for asset in assets
      ]
  ```

  Preserve the existing ZIP result semantics: source-level ZIP errors remain in the current ZIP helper response model; do not silently mark failed ZIP members as assets.

- [ ] **Step 5: Add the project upload route**

  Add it before `GET /projects/{project_id}/assets` so the static `/upload` route is matched before the dynamic asset routes.

  ```python
  @router.post(
      "/projects/{project_id}/assets/upload",
      response_model=list[ResearchAssetResponse],
      status_code=status.HTTP_201_CREATED,
  )
  async def upload_project_asset(
      project_id: str,
      file: UploadFile,
      user: User = Depends(get_current_user),
      db: AsyncSession = Depends(get_db),
  ):
      await _get_readable_project(project_id, user, db)
      return await _upload_project_assets(
          file=file,
          project_id=project_id,
          origin_session_id=None,
          user=user,
          db=db,
      )
  ```

- [ ] **Step 6: Run the focused backend tests**

  Run: `backend/.venv/bin/pytest tests/test_research_assets.py -k 'project_asset_upload' -v`

  Expected: both tests pass; the success case is `201`, and the unassigned researcher receives `404` without creating a source or asset.

- [ ] **Step 7: Commit the backend project-upload unit**

  ```bash
  git add backend/app/api/research_assets.py tests/test_research_assets.py
  git commit -m "feat: add project asset upload endpoint"
  ```

### Task 2: Make session uploads project-exclusive and immediately attached

**Files:**
- Modify: `tests/test_research_assets.py`
- Modify: `backend/app/api/sources.py`
- Modify: `backend/app/api/research_assets.py`

- [ ] **Step 1: Add a failing session-upload test**

  ```python
  async def test_session_upload_creates_project_asset_and_session_link(
      client: AsyncClient, pi_headers, pi_user: User, db: AsyncSession
  ):
      project = Project(name="Session upload project", description=None)
      db.add(project)
      await db.flush()
      db.add(ResearcherProject(project_id=project.id, researcher_id=pi_user.id, role="owner"))
      await db.commit()
      session_response = await client.post(
          "/api/v1/sessions", json={"title": "Upload context", "project_id": project.id}, headers=pi_headers
      )

      response = await client.post(
          f"/api/v1/sessions/{session_response.json()['id']}/sources",
          files={"file": ("session-paper.pdf", b"%PDF-1.4 session\n%%EOF", "application/pdf")},
          headers=pi_headers,
      )

      assert response.status_code == 201
      source_id = response.json()["id"]
      asset = await db.scalar(select(ResearchAsset).where(ResearchAsset.source_id == source_id))
      assert asset is not None
      assert asset.visibility_scope == "project"
      assert asset.origin_project_id == project.id
      assert asset.origin_session_id == session_response.json()["id"]
      assert await db.scalar(
          select(SessionSource).where(
              SessionSource.session_id == session_response.json()["id"],
              SessionSource.source_id == source_id,
          )
      ) is not None
  ```

- [ ] **Step 2: Run the test to verify the current behavior is insufficient**

  Run: `backend/.venv/bin/pytest tests/test_research_assets.py::test_session_upload_creates_project_asset_and_session_link -v`

  Expected: FAIL because the current `upload_source` path only creates a `Source` and `SessionSource`, not a project-origin `ResearchAsset`.

- [ ] **Step 3: Add a session-aware upload wrapper in `sources.py`**

  Import `_upload_project_assets` and `_response` from `app.api.research_assets`, and use the session's project id. Keep existing `source_id` form posts unchanged so linking existing eligible sources remains backward compatible.

  ```python
  async def _upload_project_source_for_session(
      *, session_id: str, file: UploadFile, user: User, db: AsyncSession
  ) -> SourceResponse | ZipUploadResponse:
      session = await _get_session_for_user(session_id, user, db)
      if session.project_id is None:
          raise HTTPException(status_code=400, detail="Session must belong to a project before uploading materials")
      assets = await _upload_project_assets(
          file=file,
          project_id=session.project_id,
          origin_session_id=session.id,
          user=user,
          db=db,
      )
      source_ids = [asset.source_id for asset in assets if asset.source_id]
      for source_id in source_ids:
          await _ensure_session_link(session.id, source_id, db)
      await db.commit()
      sources = list((await db.scalars(select(Source).where(Source.id.in_(source_ids)))).all())
      responses = await _build_source_responses(sources, db, user.id)
      if file.filename and file.filename.lower().endswith(".zip"):
          return ZipUploadResponse(sources=responses, errors=[])
      return responses[0]
  ```

  Replace only the `if file:` branch of `upload_source` with a call to this wrapper. Preserve existing error propagation, 300-second client timeout, duplicate error payloads, and the existing `_link_existing_source` branch.

- [ ] **Step 4: Run focused regression tests**

  Run: `backend/.venv/bin/pytest tests/test_research_assets.py -k 'session_upload or project_asset_upload' -v`

  Expected: the new session test passes; existing duplicate-upload tests keep returning their established safe `409` details.

- [ ] **Step 5: Commit the session upload behavior**

  ```bash
  git add backend/app/api/sources.py backend/app/api/research_assets.py tests/test_research_assets.py
  git commit -m "feat: materialize session uploads in projects"
  ```

### Task 3: Lock session linking discovery to the approved categories

**Files:**
- Modify: `tests/test_sessions.py`
- Modify: `backend/app/api/sessions.py`

- [ ] **Step 1: Add a failing category test**

  Build four active source-backed assets for a member's project: a `lab_public` asset, a user-owned `project` asset linked to the current project, a user-owned lab-private asset not linked to the project, and another user's lab-private asset. Attach the project asset once, then request the selector endpoint.

  ```python
  response = await client.get(
      f"/api/v1/sessions/{session.id}/available-sources", headers=researcher_headers
  )

  assert response.status_code == 200
  returned = {(item["category"], item["source"]["id"]) for item in response.json()}
  assert ("lab_public", lab_public_source.id) in returned
  assert ("project", project_source.id) not in returned
  assert ("my_materials", own_private_source.id) not in returned
  assert all(source_id != other_private_source.id for _, source_id in returned)
  ```

- [ ] **Step 2: Run the test to record the current over-broad behavior**

  Run: `backend/.venv/bin/pytest tests/test_sessions.py -k 'available_sources' -v`

  Expected: FAIL because the existing `asset.owner_id == user.id` fallback exposes a user-owned `lab_private` asset before it has been approved and linked to the project.

- [ ] **Step 3: Narrow `_categorize_available_source`**

  Keep project-linked assets first, then lab-public assets, then user-owned non-private assets. A private asset must only enter through the project-link branch (which exists only after the established request-and-approval flow).

  ```python
  async def _categorize_available_source(
      db: AsyncSession, project_id: str | None, user: User, asset: ResearchAsset
  ) -> str | None:
      if project_id:
          project_link = await db.scalar(
              select(ProjectAssetLink).where(
                  ProjectAssetLink.asset_id == asset.id,
                  ProjectAssetLink.project_id == project_id,
              )
          )
          if project_link is not None:
              return "project"
      if asset.visibility_scope == "lab_public":
          return "lab_public"
      if asset.owner_id == user.id and asset.visibility_scope != "lab_private":
          return "my_materials"
      return None
  ```

- [ ] **Step 4: Run category tests**

  Run: `backend/.venv/bin/pytest tests/test_sessions.py -k 'available_sources' -v`

  Expected: PASS. Already-linked sources are absent, lab public remains available, and both unapproved private assets are excluded.

- [ ] **Step 5: Commit the selector policy**

  ```bash
  git add backend/app/api/sessions.py tests/test_sessions.py
  git commit -m "fix: limit session material discovery"
  ```

### Task 4: Add the project-assets upload control

**Files:**
- Modify: `frontend/src/pages/ProjectAssets.tsx`
- Modify: `frontend/src/locales/en-US.json`
- Modify: `frontend/src/locales/zh-CN.json`

- [ ] **Step 1: Add localized strings**

  Add these keys under the existing `library` and `source` groups, using the same nesting in both locale files.

  ```json
  {
    "projectAssets": {
      "uploadMaterial": "Upload Material",
      "uploadingMaterial": "Uploading material..."
    }
  }
  ```

  ```json
  {
    "projectAssets": {
      "uploadMaterial": "上传资料",
      "uploadingMaterial": "正在上传资料…"
    }
  }
  ```

- [ ] **Step 2: Add upload state and a refresh helper**

  In `ProjectAssets.tsx`, place state alongside the existing list/loading state and extract the existing list request into one reusable function.

  ```tsx
  const [uploading, setUploading] = useState(false);

  const loadAssets = useCallback(async () => {
    if (!projectId) return;
    const { data } = await apiClient.get(`/projects/${projectId}/assets`);
    setAssets(data);
  }, [projectId]);
  ```

- [ ] **Step 3: Implement the project upload callback**

  Reuse the file acceptance and duplicate-dialog helpers already imported by this page. Do not optimistically add an asset: successful parsing/materialization must be reloaded from the server.

  ```tsx
  const handleProjectUpload = async (file: File) => {
    if (!isAcceptedUploadFile(file) || !projectId) return false;
    setUploading(true);
    const formData = new FormData();
    formData.append('file', file);
    try {
      await apiClient.post(`/projects/${projectId}/assets/upload`, formData, { timeout: 300000 });
      await loadAssets();
      message.success(t('source.uploadSuccess'));
    } catch (error: unknown) {
      const duplicateInfo = getDuplicateUploadInfo(error);
      if (duplicateInfo) {
        showDuplicateUploadModal({ info: duplicateInfo, t });
      } else {
        notification.error({ message: t('source.uploadFailed'), duration: 0 });
      }
    } finally {
      setUploading(false);
    }
    return false;
  };
  ```

- [ ] **Step 4: Put the upload button in the page header**

  Use the existing Ant Design `Upload` component and `UploadOutlined`; retain all existing source labels and publish/unlink actions.

  ```tsx
  <Upload beforeUpload={handleProjectUpload} showUploadList={false} multiple accept=".pdf,.zip">
    <Button icon={<UploadOutlined />} loading={uploading}>
      {uploading ? t('projectAssets.uploadingMaterial') : t('projectAssets.uploadMaterial')}
    </Button>
  </Upload>
  ```

- [ ] **Step 5: Build the frontend**

  Run: `cd frontend && npm run build`

  Expected: Vite completes without TypeScript errors or missing i18n-key-related failures.

- [ ] **Step 6: Commit the project page UI**

  ```bash
  git add frontend/src/pages/ProjectAssets.tsx frontend/src/locales/en-US.json frontend/src/locales/zh-CN.json
  git commit -m "feat: add project material upload control"
  ```

### Task 5: Align session UI with project-scoped upload and linking

**Files:**
- Modify: `frontend/src/pages/Session.tsx`
- Modify: `frontend/src/locales/en-US.json`
- Modify: `frontend/src/locales/zh-CN.json`

- [ ] **Step 1: Extract a session-source refresh helper**

  ```tsx
  const loadSessionSources = useCallback(async () => {
    if (!sessionId) return;
    const { data } = await apiClient.get<Source[]>(`/sessions/${sessionId}/sources`);
    setSources(data);
    setSelectedSourceIds((current) => current.filter((id) => data.some((source) => source.id === id)));
  }, [sessionId]);
  ```

- [ ] **Step 2: Replace optimistic upload insertion with server refresh**

  Keep accepted types, duplicate dialog, timeout, and ZIP warning display. After a successful `POST /sessions/{sessionId}/sources`, call `await loadSessionSources()` so a session upload that materializes a project asset is rendered from canonical source data.

  ```tsx
  const { data } = await apiClient.post(`/sessions/${sessionId}/sources`, formData, { timeout: 300000 });
  await loadSessionSources();
  if (isZip && data.errors?.length) {
    data.errors.forEach((error: string) => notification.warning({ message: error, duration: 0 }));
  }
  ```

- [ ] **Step 3: Refresh after linking existing material**

  Replace append-only state updates in `linkSource` with a refresh, preventing duplicates when the session automatically contains all project sources.

  ```tsx
  await apiClient.post(`/sessions/${sessionId}/sources`, formData);
  await loadSessionSources();
  setShowLinkModal(false);
  ```

- [ ] **Step 4: Make all user-facing fallback errors localized**

  Replace the hard-coded fallback strings in the session linking/removal handlers with existing or new `source.linkFailed` and `source.removeFailed` keys in both locale files.

  ```tsx
  message.error(typeof detail === 'string' ? detail : t('source.linkFailed'));
  ```

- [ ] **Step 5: Build the frontend**

  Run: `cd frontend && npm run build`

  Expected: PASS. The upload control remains disabled only while an upload is in progress; the link dialog still groups Project, Lab Public, and My Materials.

- [ ] **Step 6: Commit the session UI alignment**

  ```bash
  git add frontend/src/pages/Session.tsx frontend/src/locales/en-US.json frontend/src/locales/zh-CN.json
  git commit -m "fix: refresh session materials after upload"
  ```

### Task 6: Run full targeted verification and prepare handoff

**Files:**
- Modify: no source files expected

- [ ] **Step 1: Run all affected backend tests**

  Run: `backend/.venv/bin/pytest tests/test_research_assets.py tests/test_sessions.py -v`

  Expected: PASS. This verifies source duplicate handling, private approval boundaries, project linking, project upload, session upload, and available-source categorization together.

- [ ] **Step 2: Run the production frontend build**

  Run: `cd frontend && npm run build`

  Expected: PASS.

- [ ] **Step 3: Run changed-file pre-commit checks**

  Run: `pre-commit run --files backend/app/api/research_assets.py backend/app/api/sources.py backend/app/api/sessions.py tests/test_research_assets.py tests/test_sessions.py frontend/src/pages/ProjectAssets.tsx frontend/src/pages/Session.tsx frontend/src/locales/en-US.json frontend/src/locales/zh-CN.json`

  Expected: PASS. If a formatter changes files, rerun the two test/build commands before committing that formatter output.

- [ ] **Step 4: Commit verification-only formatting changes if any**

  ```bash
  git status --short
  git add backend/app/api/research_assets.py backend/app/api/sources.py backend/app/api/sessions.py tests/test_research_assets.py tests/test_sessions.py frontend/src/pages/ProjectAssets.tsx frontend/src/pages/Session.tsx frontend/src/locales/en-US.json frontend/src/locales/zh-CN.json
  git commit -m "chore: verify project material uploads"
  ```

  Skip this commit when `git status --short` shows no tracked changes from verification.

## Self-review

- **Spec coverage:** Task 1 implements a project member upload, project scope, project link, no automatic lab publication, and access denial. Task 2 ensures session upload is project-origin and immediately attached. Task 3 preserves the three eligible linking groups, prevents duplicates, and excludes unapproved private assets. Tasks 4–5 add/reuse upload/link controls, localized errors, duplicate behavior, and server refresh. Task 6 verifies the full path.
- **Placeholder scan:** No deferred implementation markers are used. The ZIP helper note preserves the existing error contract instead of inventing a new one.
- **Type consistency:** Project upload returns `list[ResearchAssetResponse]`; session upload keeps its existing `SourceResponse | ZipUploadResponse` contract after converting materialized asset source ids back into source responses. Session selectors continue to consume `AvailableSourceResponse`.
