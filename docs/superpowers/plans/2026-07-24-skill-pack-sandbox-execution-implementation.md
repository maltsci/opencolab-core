# Skill-Pack Sandbox Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let admins upload skill packs (zip with `SKILL.md`) that become recommended tasks; running such a task prepares a per-run sandbox workspace (pack files + project materials as parsed text) and lets codex plan and execute autonomously in the sandbox.

**Architecture:** New `skill_packs` table + local file storage, admin CRUD under `/admin/skill-packs`, automatic task binding (`skill-pack-{id}` tasks with a `skill_pack_id` column). Execution reuses the existing `OrchestrationRun` model and `run_codex_runtime`; a new service prepares `skill-runs/{run_id}` workspaces with pack files and `materials/*.md` exports, and a new orchestration route runs them. Frontend adds an admin Skill Packs page and a session branch for pack-bound tasks.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic v2, Alembic, pytest/httpx, React, TypeScript, Ant Design, react-i18next.

---

## File map

- `backend/app/models/skill_pack.py` — new `SkillPackRecord` (id + version composite PK).
- `backend/app/models/task_definition.py` — add nullable `skill_pack_id` column.
- `backend/app/models/__init__.py` — register the new model.
- `backend/app/schemas/skill_pack.py` — `SkillPackResponse`, `SkillPackUpdateRequest`.
- `backend/app/schemas/task.py` — expose `skill_pack_id`.
- `backend/app/schemas/orchestration.py` — `SkillPackRunCreateRequest`.
- `backend/app/core/config.py` — add `skill_pack_dir` setting.
- `backend/alembic/versions/r9s0t1u2v3w4_add_skill_packs.py` — new table + column; merges the two current heads.
- `backend/app/services/skill_pack_service.py` — zip validation/storage, task binding, workspace preparation, prompt builder.
- `backend/app/api/admin.py` — `/admin/skill-packs*` CRUD.
- `backend/app/services/orchestration_service.py` — `execute_skill_pack_run`.
- `backend/app/api/orchestration.py` — `POST /sessions/{id}/orchestration-runs/skill-pack`.
- `tests/test_skill_packs.py` — all backend tests for the above.
- `frontend/src/types/task.ts` — `skill_pack_id` field + codex runtime detection.
- `frontend/src/pages/Session.tsx` — route pack-bound tasks to the new endpoint.
- `frontend/src/pages/admin/SkillPacks.tsx` — admin management page.
- `frontend/src/App.tsx` — route + nav entry.
- `frontend/src/locales/en-US.json`, `frontend/src/locales/zh-CN.json` — i18n keys.

### Task 1: Skill pack model, migration, schemas, config

**Files:**
- Create: `backend/app/models/skill_pack.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/models/task_definition.py`
- Create: `backend/app/schemas/skill_pack.py`
- Modify: `backend/app/schemas/task.py`
- Modify: `backend/app/core/config.py`
- Create: `backend/alembic/versions/r9s0t1u2v3w4_add_skill_packs.py`
- Test: `tests/test_skill_packs.py`

- [ ] **Step 1: Write a failing model/schema test**

Create `tests/test_skill_packs.py`:

```python
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.skill_pack import SkillPackRecord
from app.schemas.skill_pack import SkillPackResponse

pytestmark = pytest.mark.asyncio


async def test_skill_pack_record_persists_and_serializes(db: AsyncSession):
    pack = SkillPackRecord(
        id="gap-hunter",
        version=1,
        name="Gap Hunter",
        description="Find research gaps",
        storage_path="gap-hunter/1",
        is_enabled=True,
        created_by=None,
    )
    db.add(pack)
    await db.commit()

    response = SkillPackResponse.model_validate(pack)
    assert response.id == "gap-hunter"
    assert response.version == 1
    assert response.task_id == "skill-pack-gap-hunter"
    assert response.is_enabled is True
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `backend/.venv/bin/pytest tests/test_skill_packs.py -v -p no:cacheprovider`
Expected: FAIL — `ModuleNotFoundError: app.models.skill_pack`.

- [ ] **Step 3: Create the model, register it, and extend the task model**

Create `backend/app/models/skill_pack.py`:

```python
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SkillPackRecord(Base):
    __tablename__ = "skill_packs"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    storage_path: Mapped[str] = mapped_column(String(500))
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=text("true"),
    )
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
```

In `backend/app/models/__init__.py`, add beside the other model imports:

```python
from app.models.skill_pack import SkillPackRecord
```

In `backend/app/models/task_definition.py`, add the column after `workflow_id`:

```python
    skill_pack_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
```

- [ ] **Step 4: Create the schema and expose skill_pack_id on tasks**

Create `backend/app/schemas/skill_pack.py`:

```python
from datetime import datetime

from pydantic import BaseModel, computed_field


class SkillPackResponse(BaseModel):
    id: str
    version: int
    name: str
    description: str
    is_enabled: bool
    created_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}

    @computed_field
    @property
    def task_id(self) -> str:
        return f"skill-pack-{self.id}"


class SkillPackUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    is_enabled: bool | None = None
```

In `backend/app/schemas/task.py`, add to `TaskDefinitionBase` after `workflow_id: str`:

```python
    skill_pack_id: str | None = None
```

- [ ] **Step 5: Add the config setting**

In `backend/app/core/config.py`, directly after `upload_dir: str = "./uploads"` (line 67):

```python
    skill_pack_dir: str = "./skill-packs"
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `backend/.venv/bin/pytest tests/test_skill_packs.py -v -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 7: Write the Alembic migration**

The repo currently has two heads (`l3m4n5o6p7q8` and `q8r9s0t1u2`); this migration merges them. Create `backend/alembic/versions/r9s0t1u2v3w4_add_skill_packs.py`:

```python
"""add skill packs table and task skill_pack_id

Revision ID: r9s0t1u2v3w4
Revises: l3m4n5o6p7q8, q8r9s0t1u2
Create Date: 2026-07-24 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "r9s0t1u2v3w4"
down_revision: Union[str, Sequence[str], None] = ("l3m4n5o6p7q8", "q8r9s0t1u2")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "skill_packs",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("storage_path", sa.String(length=500), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", "version"),
    )
    op.add_column(
        "task_definitions",
        sa.Column("skill_pack_id", sa.String(length=100), nullable=True),
    )
    op.create_index(
        "ix_task_definitions_skill_pack_id",
        "task_definitions",
        ["skill_pack_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_task_definitions_skill_pack_id", table_name="task_definitions")
    op.drop_column("task_definitions", "skill_pack_id")
    op.drop_table("skill_packs")
```

- [ ] **Step 8: Commit the model layer**

```bash
git add backend/app/models/skill_pack.py backend/app/models/__init__.py backend/app/models/task_definition.py backend/app/schemas/skill_pack.py backend/app/schemas/task.py backend/app/core/config.py backend/alembic/versions/r9s0t1u2v3w4_add_skill_packs.py tests/test_skill_packs.py
git commit -m "feat: add skill pack model and schemas"
```

### Task 2: Skill pack service — zip validation, storage, task binding

**Files:**
- Create: `backend/app/services/skill_pack_service.py`
- Test: `tests/test_skill_packs.py`

- [ ] **Step 1: Write failing service tests**

Append to `tests/test_skill_packs.py`:

```python
import io
import zipfile

from app.models.task_definition import TaskDefinitionRecord
from app.services.skill_pack_service import (
    SkillPackValidationError,
    get_current_skill_pack,
    store_skill_pack_zip,
)
from sqlalchemy import select

SKILL_MD = """---
name: Gap Hunter
description: Find research gaps
version: 1
---

# Instructions

Read the materials and list gaps.
"""


def make_zip(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


async def test_store_skill_pack_zip_creates_task_and_pack(
    db: AsyncSession, tmp_path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr("app.services.skill_pack_service.settings.skill_pack_dir", str(tmp_path))
    pack = await store_skill_pack_zip(
        make_zip({"SKILL.md": SKILL_MD, "scripts/helper.py": "print('hi')"}),
        db=db,
        created_by=None,
    )

    assert pack.id == "gap-hunter"
    assert pack.version == 1
    assert (tmp_path / "gap-hunter" / "1" / "SKILL.md").exists()
    assert (tmp_path / "gap-hunter" / "1" / "scripts" / "helper.py").exists()

    task = await db.scalar(
        select(TaskDefinitionRecord).where(TaskDefinitionRecord.id == "skill-pack-gap-hunter")
    )
    assert task is not None
    assert task.skill_pack_id == "gap-hunter"
    assert task.workflow_id == "skill-pack"
    assert task.result_presentation["runtime"] == "codex"

    current = await get_current_skill_pack(db, pack_id="gap-hunter")
    assert current is not None and current.version == 1


async def test_store_skill_pack_zip_bumps_version_on_reupload(
    db: AsyncSession, tmp_path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr("app.services.skill_pack_service.settings.skill_pack_dir", str(tmp_path))
    await store_skill_pack_zip(make_zip({"SKILL.md": SKILL_MD}), db=db, created_by=None)
    pack = await store_skill_pack_zip(
        make_zip({"SKILL.md": SKILL_MD.replace("Find research gaps", "Find deeper gaps")}),
        db=db,
        created_by=None,
    )

    assert pack.version == 2
    current = await get_current_skill_pack(db, pack_id="gap-hunter")
    assert current is not None and current.version == 2
    task = await db.scalar(
        select(TaskDefinitionRecord).where(TaskDefinitionRecord.id == "skill-pack-gap-hunter")
    )
    assert task.description == "Find deeper gaps"


async def test_store_skill_pack_zip_rejects_missing_skill_md(
    db: AsyncSession, tmp_path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr("app.services.skill_pack_service.settings.skill_pack_dir", str(tmp_path))
    with pytest.raises(SkillPackValidationError, match="SKILL.md"):
        await store_skill_pack_zip(make_zip({"README.md": "hi"}), db=db, created_by=None)


async def test_store_skill_pack_zip_rejects_path_traversal(
    db: AsyncSession, tmp_path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr("app.services.skill_pack_service.settings.skill_pack_dir", str(tmp_path))
    with pytest.raises(SkillPackValidationError, match="unsafe"):
        await store_skill_pack_zip(
            make_zip({"SKILL.md": SKILL_MD, "../evil.sh": "echo x"}),
            db=db,
            created_by=None,
        )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `backend/.venv/bin/pytest tests/test_skill_packs.py -k store_skill_pack -v -p no:cacheprovider`
Expected: FAIL — `ImportError: cannot import name 'SkillPackValidationError'`.

- [ ] **Step 3: Implement the service**

Create `backend/app/services/skill_pack_service.py`:

```python
import io
import json
import re
import shutil
import zipfile
from pathlib import Path

import yaml
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.skill_pack import SkillPackRecord
from app.models.task_definition import TaskDefinitionRecord

SKILL_PACK_TASK_PREFIX = "skill-pack-"
SKILL_PACK_WORKFLOW_SENTINEL = "skill-pack"
SKILL_PACK_ALLOWED_EXTENSIONS = {
    ".md", ".txt", ".py", ".sh", ".json", ".yaml", ".yml",
    ".csv", ".j2", ".jinja", ".toml",
}
SKILL_PACK_MAX_FILES = 200
SKILL_PACK_MAX_TOTAL_BYTES = 20 * 1024 * 1024

_FRONT_MATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---", flags=re.DOTALL)


class SkillPackValidationError(ValueError):
    pass


def skill_pack_task_id(pack_id: str) -> str:
    return f"{SKILL_PACK_TASK_PREFIX}{pack_id}"


def _parse_skill_md(text: str) -> dict:
    match = _FRONT_MATTER_PATTERN.match(text.strip())
    if match is None:
        raise SkillPackValidationError("SKILL.md must start with YAML front matter")
    try:
        payload = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        raise SkillPackValidationError(f"SKILL.md front matter is invalid YAML: {exc}") from exc
    if not isinstance(payload, dict) or not payload.get("name") or not payload.get("description"):
        raise SkillPackValidationError("SKILL.md front matter requires name and description")
    raw_id = str(payload.get("id") or payload["name"]).strip()
    pack_id = re.sub(r"[^a-z0-9]+", "-", raw_id.lower()).strip("-")
    if not pack_id:
        raise SkillPackValidationError("Skill pack id could not be generated from name")
    return {
        "id": pack_id,
        "name": str(payload["name"]).strip(),
        "description": str(payload["description"]).strip(),
    }


def _validate_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members = [info for info in archive.infolist() if not info.is_dir()]
    if len(members) > SKILL_PACK_MAX_FILES:
        raise SkillPackValidationError(
            f"Skill pack has too many files (max {SKILL_PACK_MAX_FILES})"
        )
    total_bytes = 0
    for info in members:
        name = info.filename
        path = Path(name)
        if path.is_absolute() or ".." in path.parts:
            raise SkillPackValidationError(f"Skill pack contains an unsafe path: {name}")
        if (info.external_attr >> 16) & 0o120000 == 0o120000:
            raise SkillPackValidationError(f"Skill pack must not contain symlinks: {name}")
        if path.suffix.lower() not in SKILL_PACK_ALLOWED_EXTENSIONS:
            raise SkillPackValidationError(f"File type is not allowed in a skill pack: {name}")
        total_bytes += info.file_size
    if total_bytes > SKILL_PACK_MAX_TOTAL_BYTES:
        raise SkillPackValidationError("Skill pack is too large (max 20 MB uncompressed)")
    if "SKILL.md" not in {info.filename for info in members}:
        raise SkillPackValidationError("Skill pack must contain SKILL.md at the archive root")
    return members


async def get_current_skill_pack(db: AsyncSession, *, pack_id: str) -> SkillPackRecord | None:
    return await db.scalar(
        select(SkillPackRecord)
        .where(SkillPackRecord.id == pack_id)
        .order_by(SkillPackRecord.version.desc())
        .limit(1)
    )


async def _upsert_bound_task(db: AsyncSession, pack: SkillPackRecord) -> None:
    task = await db.scalar(
        select(TaskDefinitionRecord).where(
            TaskDefinitionRecord.id == skill_pack_task_id(pack.id)
        )
    )
    if task is None:
        db.add(
            TaskDefinitionRecord(
                id=skill_pack_task_id(pack.id),
                version=pack.version,
                name=pack.name,
                description=pack.description,
                workflow_id=SKILL_PACK_WORKFLOW_SENTINEL,
                skill_pack_id=pack.id,
                input_schema={"type": "object"},
                starter_prompts=[f"Use {pack.name} for the current project task."],
                project_context_policy={
                    "inherit_project_sources": True,
                    "include_research_memory": True,
                },
                result_presentation={
                    "type": "assistant_message",
                    "runtime": "codex",
                },
                is_enabled=pack.is_enabled,
                project_ids=[],
            )
        )
        return
    task.version = pack.version
    task.name = pack.name
    task.description = pack.description
    task.skill_pack_id = pack.id
    task.is_enabled = pack.is_enabled


async def store_skill_pack_zip(
    content: bytes,
    *,
    db: AsyncSession,
    created_by: str | None,
) -> SkillPackRecord:
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise SkillPackValidationError("Uploaded file is not a valid zip archive") from exc

    with archive:
        members = _validate_members(archive)
        skill_md = archive.read("SKILL.md").decode("utf-8")
        meta = _parse_skill_md(skill_md)

        latest_version = await db.scalar(
            select(func.max(SkillPackRecord.version)).where(
                SkillPackRecord.id == meta["id"]
            )
        )
        version = (latest_version or 0) + 1
        storage_path = f"{meta['id']}/{version}"
        target_dir = Path(settings.skill_pack_dir) / storage_path
        if target_dir.exists():
            shutil.rmtree(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        for info in members:
            target = target_dir / info.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(info))

    pack = SkillPackRecord(
        id=meta["id"],
        version=version,
        name=meta["name"],
        description=meta["description"],
        storage_path=storage_path,
        is_enabled=True,
        created_by=created_by,
    )
    db.add(pack)
    await _upsert_bound_task(db, pack)
    await db.commit()
    await db.refresh(pack)
    return pack
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `backend/.venv/bin/pytest tests/test_skill_packs.py -v -p no:cacheprovider`
Expected: 5 passed.

- [ ] **Step 5: Commit the service**

```bash
git add backend/app/services/skill_pack_service.py tests/test_skill_packs.py
git commit -m "feat: add skill pack storage and task binding"
```

### Task 3: Admin skill-pack API

**Files:**
- Modify: `backend/app/api/admin.py`
- Test: `tests/test_skill_packs.py`

- [ ] **Step 1: Write failing API tests**

Append to `tests/test_skill_packs.py`:

```python
from httpx import AsyncClient


async def test_admin_uploads_skill_pack(
    client: AsyncClient, auth_headers, tmp_path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr("app.services.skill_pack_service.settings.skill_pack_dir", str(tmp_path))
    response = await client.post(
        "/api/v1/admin/skill-packs",
        files={"file": ("gap-hunter.zip", make_zip({"SKILL.md": SKILL_MD}), "application/zip")},
        headers=auth_headers,
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["id"] == "gap-hunter"
    assert payload["task_id"] == "skill-pack-gap-hunter"

    listing = await client.get("/api/v1/admin/skill-packs", headers=auth_headers)
    assert [item["id"] for item in listing.json()] == ["gap-hunter"]

    versions = await client.get(
        "/api/v1/admin/skill-packs/gap-hunter/versions", headers=auth_headers
    )
    assert [item["version"] for item in versions.json()] == [1]

    task_response = await client.get("/api/v1/tasks", headers=auth_headers)
    bound = [item for item in task_response.json() if item["id"] == "skill-pack-gap-hunter"]
    assert bound and bound[0]["skill_pack_id"] == "gap-hunter"


async def test_admin_skill_pack_upload_rejects_non_admin(
    client: AsyncClient, researcher_headers
):
    response = await client.post(
        "/api/v1/admin/skill-packs",
        files={"file": ("pack.zip", make_zip({"SKILL.md": SKILL_MD}), "application/zip")},
        headers=researcher_headers,
    )
    assert response.status_code == 403


async def test_admin_skill_pack_patch_and_delete(
    client: AsyncClient, auth_headers, tmp_path, monkeypatch: pytest.MonkeyPatch, db: AsyncSession
):
    monkeypatch.setattr("app.services.skill_pack_service.settings.skill_pack_dir", str(tmp_path))
    await client.post(
        "/api/v1/admin/skill-packs",
        files={"file": ("pack.zip", make_zip({"SKILL.md": SKILL_MD}), "application/zip")},
        headers=auth_headers,
    )

    patch = await client.patch(
        "/api/v1/admin/skill-packs/gap-hunter",
        json={"is_enabled": False},
        headers=auth_headers,
    )
    assert patch.status_code == 200
    assert patch.json()["is_enabled"] is False
    task = await db.scalar(
        select(TaskDefinitionRecord).where(TaskDefinitionRecord.id == "skill-pack-gap-hunter")
    )
    assert task.is_enabled is False

    delete = await client.delete("/api/v1/admin/skill-packs/gap-hunter", headers=auth_headers)
    assert delete.status_code == 204
    assert await db.scalar(
        select(SkillPackRecord).where(SkillPackRecord.id == "gap-hunter")
    ) is None
    assert not (tmp_path / "gap-hunter").exists()
    assert task is not None  # task row kept, disabled


async def test_admin_skill_pack_upload_validation_error(
    client: AsyncClient, auth_headers, tmp_path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr("app.services.skill_pack_service.settings.skill_pack_dir", str(tmp_path))
    response = await client.post(
        "/api/v1/admin/skill-packs",
        files={"file": ("pack.zip", make_zip({"README.md": "hi"}), "application/zip")},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert "SKILL.md" in response.json()["detail"]
```

Add `from app.models.skill_pack import SkillPackRecord` to the test imports.

- [ ] **Step 2: Run the API tests to verify they fail**

Run: `backend/.venv/bin/pytest tests/test_skill_packs.py -k admin -v -p no:cacheprovider`
Expected: FAIL — 404 on `/api/v1/admin/skill-packs`.

- [ ] **Step 3: Implement the admin endpoints**

In `backend/app/api/admin.py`, add to the imports:

```python
import shutil
from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings
from app.models.skill_pack import SkillPackRecord
from app.schemas.skill_pack import SkillPackResponse, SkillPackUpdateRequest
from app.services.skill_pack_service import (
    SkillPackValidationError,
    get_current_skill_pack,
    skill_pack_task_id,
    store_skill_pack_zip,
)
```

Note: `fastapi` already imports `APIRouter, Depends, HTTPException, status` on line 2 — extend that same import with `UploadFile` instead of adding a second import line. `Path`/`shutil`/`settings` are only needed by the delete handler below.

Add the endpoints directly after the `install_skill_from_url` handler (after line 492):

```python
# --- Skill Packs ---


def _skill_pack_response(record: SkillPackRecord) -> SkillPackResponse:
    return SkillPackResponse.model_validate(record)


@router.post(
    "/skill-packs",
    response_model=SkillPackResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_skill_pack(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(admin_dep),
):
    try:
        pack = await store_skill_pack_zip(
            await file.read(),
            db=db,
            created_by=current_user.id,
        )
    except SkillPackValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _skill_pack_response(pack)


@router.get("/skill-packs", response_model=list[SkillPackResponse])
async def list_skill_packs(
    db: AsyncSession = Depends(get_db),
    _=Depends(admin_dep),
):
    result = await db.execute(
        select(SkillPackRecord).order_by(SkillPackRecord.id, SkillPackRecord.version.desc())
    )
    current_by_id: dict[str, SkillPackRecord] = {}
    for record in result.scalars().all():
        current_by_id.setdefault(record.id, record)
    return [_skill_pack_response(record) for record in current_by_id.values()]


@router.get("/skill-packs/{pack_id}/versions", response_model=list[SkillPackResponse])
async def list_skill_pack_versions(
    pack_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(admin_dep),
):
    result = await db.execute(
        select(SkillPackRecord)
        .where(SkillPackRecord.id == pack_id)
        .order_by(SkillPackRecord.version.desc())
    )
    records = list(result.scalars().all())
    if not records:
        raise HTTPException(status_code=404, detail="Skill pack not found")
    return [_skill_pack_response(record) for record in records]


@router.patch("/skill-packs/{pack_id}", response_model=SkillPackResponse)
async def update_skill_pack(
    pack_id: str,
    body: SkillPackUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(admin_dep),
):
    pack = await get_current_skill_pack(db, pack_id=pack_id)
    if pack is None:
        raise HTTPException(status_code=404, detail="Skill pack not found")
    for field, value in body.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(pack, field, value)

    task = await db.scalar(
        select(TaskDefinitionRecord).where(
            TaskDefinitionRecord.id == skill_pack_task_id(pack_id)
        )
    )
    if task is not None:
        task.name = pack.name
        task.description = pack.description
        task.is_enabled = pack.is_enabled
    await db.commit()
    await db.refresh(pack)
    return _skill_pack_response(pack)


@router.delete("/skill-packs/{pack_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_skill_pack(
    pack_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(admin_dep),
):
    result = await db.execute(
        select(SkillPackRecord).where(SkillPackRecord.id == pack_id)
    )
    records = list(result.scalars().all())
    if not records:
        raise HTTPException(status_code=404, detail="Skill pack not found")
    for record in records:
        await db.delete(record)

    task = await db.scalar(
        select(TaskDefinitionRecord).where(
            TaskDefinitionRecord.id == skill_pack_task_id(pack_id)
        )
    )
    if task is not None:
        task.is_enabled = False

    pack_dir = Path(settings.skill_pack_dir) / pack_id
    if pack_dir.exists():
        shutil.rmtree(pack_dir)
    await db.commit()
    return None
```

- [ ] **Step 4: Run the API tests to verify they pass**

Run: `backend/.venv/bin/pytest tests/test_skill_packs.py -v -p no:cacheprovider`
Expected: all tests pass.

- [ ] **Step 5: Commit the admin API**

```bash
git add backend/app/api/admin.py tests/test_skill_packs.py
git commit -m "feat: add admin skill pack endpoints"
```

### Task 4: Run workspace preparation and prompt builder

**Files:**
- Modify: `backend/app/services/skill_pack_service.py`
- Test: `tests/test_skill_packs.py`

- [ ] **Step 1: Write failing workspace tests**

Append to `tests/test_skill_packs.py`:

```python
from pathlib import Path

from app.models.project import Project
from app.models.research_asset import ProjectAssetLink, ResearchAsset
from app.models.session import Session
from app.models.source import Chunk, Source
from app.models.user import User, Workspace
from app.services.skill_pack_service import (
    build_skill_pack_prompt,
    prepare_skill_run_workspace,
)


async def _always_authorized(**kwargs) -> bool:
    return True


async def _seed_project_material(db: AsyncSession, user: User):
    workspace = await db.scalar(select(Workspace).where(Workspace.researcher_id == user.id))
    project = Project(name="Pack project", description=None)
    source = Source(
        type="file", name="paper.pdf", content_hash="h1", content_path="x",
        processing_state="ready", owner_id=user.id,
    )
    db.add_all([project, source])
    await db.flush()
    db.add_all([
        Chunk(source_id=source.id, chunk_index=0, text="First part."),
        Chunk(source_id=source.id, chunk_index=1, text="Second part."),
    ])
    asset = ResearchAsset(
        asset_type="uploaded_file",
        title="paper.pdf",
        owner_id=user.id,
        steward_user_id=user.id,
        visibility_scope="project",
        origin_project_id=project.id,
        source_id=source.id,
    )
    db.add(asset)
    await db.flush()
    db.add(
        ProjectAssetLink(
            project_id=project.id, asset_id=asset.id,
            created_by=user.id, link_type="source",
        )
    )
    session = Session(workspace_id=workspace.id, project_id=project.id, title="s")
    db.add(session)
    await db.commit()
    return project, source, session


async def test_prepare_skill_run_workspace_exports_parsed_materials(
    db: AsyncSession, admin_user: User, tmp_path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr("app.services.skill_pack_service.settings.skill_pack_dir", str(tmp_path / "packs"))
    monkeypatch.setattr(
        "app.services.skill_pack_service.settings.codex_runtime_workspace_dir",
        str(tmp_path / "workspace"),
    )
    monkeypatch.setattr(
        "app.services.skill_pack_service.settings.codex_runtime_sandbox_workspace_dir",
        "/workspace",
    )
    monkeypatch.setattr(
        "app.services.research_context.can_user_use_source_in_agent",
        _always_authorized,
    )
    pack = await store_skill_pack_zip(
        make_zip({"SKILL.md": SKILL_MD, "scripts/helper.py": "print('hi')"}),
        db=db,
        created_by=admin_user.id,
    )
    project, source, session = await _seed_project_material(db, admin_user)

    sandbox_cwd = await prepare_skill_run_workspace(
        db=db, run_id="run-1", pack=pack, session=session, user=admin_user
    )

    assert sandbox_cwd == "/workspace/skill-runs/run-1"
    run_dir = tmp_path / "workspace" / "skill-runs" / "run-1"
    assert (run_dir / "SKILL.md").exists()
    assert (run_dir / "scripts" / "helper.py").exists()
    material = (run_dir / "materials" / f"{source.id}.md").read_text(encoding="utf-8")
    assert "First part." in material and "Second part." in material
    manifest = json.loads((run_dir / "materials" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["materials"][0]["source_id"] == source.id
    assert manifest["materials"][0]["status"] == "exported"


def test_build_skill_pack_prompt_includes_goal_and_memory():
    from app.services.research_context import ResearchContextMemory, ResearchExecutionContext

    context = ResearchExecutionContext(
        memories=[
            ResearchContextMemory(id="m1", type="note", title="Idea", content="Remember this")
        ]
    )
    prompt = build_skill_pack_prompt(goal="Find the gaps", memories=context)
    assert "./SKILL.md" in prompt
    assert "./materials/manifest.json" in prompt
    assert "Find the gaps" in prompt
    assert "Remember this" in prompt
```

Add `import json` to the test file imports if not present.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `backend/.venv/bin/pytest tests/test_skill_packs.py -k 'prepare_skill_run or build_skill_pack_prompt' -v -p no:cacheprovider`
Expected: FAIL — cannot import `prepare_skill_run_workspace`.

- [ ] **Step 3: Implement workspace preparation and the prompt builder**

In `backend/app/services/skill_pack_service.py`, extend the imports:

```python
from app.models.research_asset import ProjectAssetLink  # noqa: F401  (used by collect query)
from app.models.session import Session
from app.models.source import Chunk, Source
from app.models.trace import SourceExtraction
from app.models.user import User
from app.services.research_context import (
    ResearchExecutionContext,
    collect_project_source_ids,
)
```

Append:

```python
def build_skill_pack_prompt(*, goal: str, memories: ResearchExecutionContext) -> str:
    parts = [
        "Read ./SKILL.md and follow it exactly to accomplish the user's goal below.",
        (
            "Project materials (parsed text) are in ./materials/ — "
            "see ./materials/manifest.json for the index."
        ),
        "Write your final answer as your last message.",
        "",
        "## User Goal",
        goal,
    ]
    if memories.memories:
        parts.append("## Research Memory")
        for memory in memories.memories:
            title = memory.title or memory.id
            parts.append(f"### {memory.type}: {title}\n\n{memory.content or ''}")
    return "\n\n".join(parts)


async def _export_source_material(db: AsyncSession, source_id: str) -> dict | None:
    source = await db.get(Source, source_id)
    chunks = list(
        (
            await db.scalars(
                select(Chunk)
                .where(Chunk.source_id == source_id)
                .order_by(Chunk.chunk_index)
            )
        ).all()
    )
    if chunks:
        body = "\n\n".join(chunk.text for chunk in chunks)
    else:
        extraction = await db.scalar(
            select(SourceExtraction).where(SourceExtraction.source_id == source_id)
        )
        if extraction is None or not extraction.structured_json:
            return None
        body = (
            "```json\n"
            + json.dumps(extraction.structured_json, ensure_ascii=False, indent=2)
            + "\n```"
        )
    title = source.name if source is not None else source_id
    header = f"# {title}\n\n- source_id: `{source_id}`\n\n"
    return {
        "filename": f"{source_id}.md",
        "content": header + body,
        "entry": {
            "source_id": source_id,
            "title": title,
            "chunks": len(chunks),
            "status": "exported",
        },
    }


async def prepare_skill_run_workspace(
    *,
    db: AsyncSession,
    run_id: str,
    pack: SkillPackRecord,
    session: Session,
    user: User,
) -> str | None:
    if not settings.codex_runtime_workspace_dir:
        return None

    run_dir = Path(settings.codex_runtime_workspace_dir) / "skill-runs" / run_id
    materials_dir = run_dir / "materials"
    materials_dir.mkdir(parents=True, exist_ok=True)

    pack_root = Path(settings.skill_pack_dir) / pack.storage_path
    for item in pack_root.rglob("*"):
        if item.is_file():
            target = run_dir / item.relative_to(pack_root)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)

    source_ids = await collect_project_source_ids(
        db=db,
        project_id=session.project_id,
        user=user,
    )
    manifest_entries: list[dict] = []
    for source_id in source_ids:
        exported = await _export_source_material(db, source_id)
        if exported is None:
            manifest_entries.append(
                {"source_id": source_id, "status": "skipped", "reason": "no parsed text"}
            )
            continue
        (materials_dir / exported["filename"]).write_text(
            exported["content"], encoding="utf-8"
        )
        manifest_entries.append(exported["entry"])
    (materials_dir / "manifest.json").write_text(
        json.dumps({"materials": manifest_entries}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    sandbox_root = settings.codex_runtime_sandbox_workspace_dir
    if not sandbox_root:
        return str(run_dir)
    return str(Path(sandbox_root) / "skill-runs" / run_id)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `backend/.venv/bin/pytest tests/test_skill_packs.py -v -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 5: Commit the workspace preparation**

```bash
git add backend/app/services/skill_pack_service.py tests/test_skill_packs.py
git commit -m "feat: prepare skill run workspaces"
```

### Task 5: Skill-pack run execution

**Files:**
- Modify: `backend/app/services/orchestration_service.py`
- Modify: `backend/app/schemas/orchestration.py`
- Modify: `backend/app/api/orchestration.py`
- Test: `tests/test_skill_packs.py`

- [ ] **Step 1: Write failing run tests**

Append to `tests/test_skill_packs.py`:

```python
from app.models.message import Message


async def _start_pack_session(
    client: AsyncClient, auth_headers, db: AsyncSession, admin_user: User,
    tmp_path, monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr("app.services.skill_pack_service.settings.skill_pack_dir", str(tmp_path / "packs"))
    monkeypatch.setattr(
        "app.services.skill_pack_service.settings.codex_runtime_workspace_dir",
        str(tmp_path / "workspace"),
    )
    monkeypatch.setattr(
        "app.services.research_context.can_user_use_source_in_agent",
        _always_authorized,
    )
    await client.post(
        "/api/v1/admin/skill-packs",
        files={"file": ("pack.zip", make_zip({"SKILL.md": SKILL_MD}), "application/zip")},
        headers=auth_headers,
    )
    project, _source, _session = await _seed_project_material(db, admin_user)
    session_response = await client.post(
        "/api/v1/sessions",
        json={
            "title": "Pack run",
            "project_id": project.id,
            "task_id": "skill-pack-gap-hunter",
        },
        headers=auth_headers,
    )
    assert session_response.status_code == 201
    return session_response.json()["id"]


async def test_skill_pack_run_persists_assistant_message(
    client: AsyncClient, auth_headers, db: AsyncSession, admin_user: User,
    tmp_path, monkeypatch: pytest.MonkeyPatch,
):
    session_id = await _start_pack_session(
        client, auth_headers, db, admin_user, tmp_path, monkeypatch
    )

    captured: dict = {}

    async def fake_run_codex_runtime(*, prompt, db, cwd=None, sandbox=None):
        captured["prompt"] = prompt
        captured["cwd"] = cwd
        return {"status": "completed", "content": "Here are the gaps."}

    monkeypatch.setattr(
        "app.services.orchestration_service.run_codex_runtime", fake_run_codex_runtime
    )

    response = await client.post(
        f"/api/v1/sessions/{session_id}/orchestration-runs/skill-pack",
        json={"goal": "Find the gaps"},
        headers=auth_headers,
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["final_message_id"] is not None
    final_message = await db.get(Message, payload["final_message_id"])
    assert final_message.content == "Here are the gaps."
    assert "Find the gaps" in captured["prompt"]
    assert captured["cwd"] is not None and "skill-runs" in captured["cwd"]


async def test_skill_pack_run_rejects_non_pack_task(
    client: AsyncClient, auth_headers, db: AsyncSession, admin_user: User
):
    project = Project(name="No pack", description=None)
    db.add(project)
    await db.flush()
    workspace = await db.scalar(select(Workspace).where(Workspace.researcher_id == admin_user.id))
    session = Session(workspace_id=workspace.id, project_id=project.id, title="s")
    db.add(session)
    await db.commit()

    response = await client.post(
        f"/api/v1/sessions/{session.id}/orchestration-runs/skill-pack",
        json={"goal": "Run something"},
        headers=auth_headers,
    )
    assert response.status_code == 400


async def test_skill_pack_run_rejects_disabled_pack(
    client: AsyncClient, auth_headers, db: AsyncSession, admin_user: User,
    tmp_path, monkeypatch: pytest.MonkeyPatch,
):
    session_id = await _start_pack_session(
        client, auth_headers, db, admin_user, tmp_path, monkeypatch
    )
    await client.patch(
        "/api/v1/admin/skill-packs/gap-hunter",
        json={"is_enabled": False},
        headers=auth_headers,
    )

    response = await client.post(
        f"/api/v1/sessions/{session_id}/orchestration-runs/skill-pack",
        json={"goal": "Find the gaps"},
        headers=auth_headers,
    )
    assert response.status_code == 409


async def test_skill_pack_run_marks_failed_on_runtime_error(
    client: AsyncClient, auth_headers, db: AsyncSession, admin_user: User,
    tmp_path, monkeypatch: pytest.MonkeyPatch,
):
    session_id = await _start_pack_session(
        client, auth_headers, db, admin_user, tmp_path, monkeypatch
    )

    async def failing_run_codex_runtime(*, prompt, db, cwd=None, sandbox=None):
        raise RuntimeError("sandbox down")

    monkeypatch.setattr(
        "app.services.orchestration_service.run_codex_runtime", failing_run_codex_runtime
    )

    response = await client.post(
        f"/api/v1/sessions/{session_id}/orchestration-runs/skill-pack",
        json={"goal": "Find the gaps"},
        headers=auth_headers,
    )
    assert response.status_code == 502
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `backend/.venv/bin/pytest tests/test_skill_packs.py -k skill_pack_run -v -p no:cacheprovider`
Expected: FAIL — 404 on `/orchestration-runs/skill-pack`.

- [ ] **Step 3: Add the request schema**

In `backend/app/schemas/orchestration.py`, append:

```python
class SkillPackRunCreateRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=10000)
    task_id: str | None = None
```

- [ ] **Step 4: Implement the execution service**

In `backend/app/services/orchestration_service.py`, extend the imports:

```python
from app.services.research_context import build_research_execution_context
from app.services.skill_pack_service import (
    build_skill_pack_prompt,
    get_current_skill_pack,
    prepare_skill_run_workspace,
)
from app.services.task_service import UnknownTaskDefinitionError
```

(`build_research_execution_context` merges into the existing `from app.services.research_context import (...)` block.)

Append after `execute_project_qa_run`:

```python
class SkillPackUnavailableError(RuntimeError):
    pass


class SkillPackRuntimeError(RuntimeError):
    pass


async def execute_skill_pack_run(
    *,
    db: AsyncSession,
    session_id: str,
    user: User,
    goal: str,
    task_id: str | None = None,
) -> OrchestrationRun:
    """Run a skill-pack-bound task inside the codex sandbox workspace."""
    session = await _get_authorized_session(db=db, session_id=session_id, user=user)
    if session.project_id is None:
        raise ValueError("Skill pack runs require a project session")
    effective_task_id = task_id or session.task_id
    if effective_task_id is None:
        raise ValueError("Task session is required for skill pack runs")
    try:
        task = await get_task_definition(
            effective_task_id,
            db,
            project_id=session.project_id,
        )
    except UnknownTaskDefinitionError as exc:
        raise ValueError("Task not found") from exc
    if not task.skill_pack_id:
        raise ValueError("Task is not bound to a skill pack")

    pack = await get_current_skill_pack(db, pack_id=task.skill_pack_id)
    if pack is None or not pack.is_enabled:
        raise SkillPackUnavailableError("Skill pack is unavailable")

    run = await create_orchestration_run(
        db=db,
        session_id=session.id,
        user=user,
        task_id=effective_task_id,
        plan_snapshot={
            "mode": "skill_pack",
            "skill_pack_id": pack.id,
            "skill_pack_version": pack.version,
        },
        output_contract_snapshot={"type": "assistant_message"},
        context_manifest={},
        allow_task_override=True,
    )
    sandbox_cwd = await prepare_skill_run_workspace(
        db=db,
        run_id=run.id,
        pack=pack,
        session=session,
        user=user,
    )
    run.context_manifest = {
        "skill_pack_id": pack.id,
        "skill_pack_version": pack.version,
        "workspace": sandbox_cwd,
    }
    memories = await build_research_execution_context(
        db=db,
        session_id=session.id,
        user_id=user.id,
        source_ids=[],
        max_memories=6,
    )
    prompt = build_skill_pack_prompt(goal=goal, memories=memories)

    await transition_orchestration_run(
        db=db,
        run_id=run.id,
        user=user,
        target_status="running",
    )
    try:
        runtime_payload = await run_codex_runtime(prompt=prompt, db=db, cwd=sandbox_cwd)
        if str(runtime_payload.get("status") or "completed") != "completed":
            raise SkillPackRuntimeError("Codex runtime did not complete the run")
        content = str(runtime_payload.get("content") or "").strip()
        if not content:
            raise SkillPackRuntimeError("Codex runtime returned an empty response")
    except Exception as exc:
        run.status = "failed"
        run.error_code = "codex_runtime_failed"
        run.error_message = "Codex runtime failed."
        await db.commit()
        if isinstance(exc, SkillPackRuntimeError):
            raise
        raise SkillPackRuntimeError("Codex runtime failed") from exc

    final_message = Message(session_id=session.id, role="assistant", content=content)
    db.add(final_message)
    await db.flush()
    run.status = "completed"
    run.final_message_id = final_message.id
    await db.commit()
    await db.refresh(run)
    return run
```

- [ ] **Step 5: Add the route**

In `backend/app/api/orchestration.py`, extend the service import with `SkillPackRuntimeError, SkillPackUnavailableError, execute_skill_pack_run`, extend the schema import with `SkillPackRunCreateRequest`, and add after `run_project_qa`:

```python
@router.post(
    "/sessions/{session_id}/orchestration-runs/skill-pack",
    response_model=OrchestrationRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def run_skill_pack(
    session_id: str,
    body: SkillPackRunCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        run = await execute_skill_pack_run(
            db=db,
            session_id=session_id,
            user=user,
            goal=body.goal,
            task_id=body.task_id,
        )
    except OrchestrationSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc
    except SkillPackUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Skill pack is unavailable",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SkillPackRuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Codex runtime failed.",
        ) from exc
    return OrchestrationRunResponse.model_validate(run)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `backend/.venv/bin/pytest tests/test_skill_packs.py tests/test_orchestration_runs.py -v -p no:cacheprovider`
Expected: all pass (existing project-qa tests unaffected).

- [ ] **Step 7: Commit the execution path**

```bash
git add backend/app/services/orchestration_service.py backend/app/schemas/orchestration.py backend/app/api/orchestration.py tests/test_skill_packs.py
git commit -m "feat: run skill packs in the codex sandbox"
```

### Task 6: Frontend task type and session routing

**Files:**
- Modify: `frontend/src/types/task.ts`
- Modify: `frontend/src/pages/Session.tsx`

- [ ] **Step 1: Expose skill_pack_id on the task type**

In `frontend/src/types/task.ts`, add to `TaskDefinition` after `workflow_id: string;`:

```ts
  skill_pack_id: string | null;
```

And in `getTaskRuntimeKind`, add as the first check:

```ts
  if (task.skill_pack_id) {
    return 'codex';
  }
```

- [ ] **Step 2: Route pack-bound tasks in the session page**

In `frontend/src/pages/Session.tsx`, inside `handleStartSelectedSessionTask` (around line 1144), directly after the `project-qa` branch and before the workflow payload branch, add:

```tsx
      if (task.skill_pack_id) {
        await apiClient.post(`/sessions/${sessionId}/orchestration-runs/skill-pack`, {
          goal: requestText,
          task_id: task.id,
        });
        await reloadMessagesAndTrace();
        setSelectedSessionTask(null);
        message.success(t('task.workspaceRunStarted'));
        return;
      }
```

- [ ] **Step 3: Build the frontend**

Run: `cd frontend && npm run build`
Expected: PASS.

- [ ] **Step 4: Commit the session routing**

```bash
git add frontend/src/types/task.ts frontend/src/pages/Session.tsx
git commit -m "feat: route skill pack tasks in sessions"
```

### Task 7: Admin skill-pack page

**Files:**
- Create: `frontend/src/pages/admin/SkillPacks.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/locales/en-US.json`
- Modify: `frontend/src/locales/zh-CN.json`

- [ ] **Step 1: Add i18n keys**

In `frontend/src/locales/en-US.json`, beside the other `admin.*` keys:

```json
  "admin.skillPacks": "Skill Packs",
  "admin.skillPacks.upload": "Upload Skill Pack",
  "admin.skillPacks.uploadSuccess": "Skill pack uploaded",
  "admin.skillPacks.uploadFailed": "Failed to upload skill pack",
  "admin.skillPacks.name": "Name",
  "admin.skillPacks.description": "Description",
  "admin.skillPacks.version": "Version",
  "admin.skillPacks.task": "Bound Task",
  "admin.skillPacks.enabled": "Enabled",
  "admin.skillPacks.updatedAt": "Updated",
  "admin.skillPacks.deleteConfirm": "Delete this skill pack? Its task will be disabled.",
  "admin.skillPacks.deleteSuccess": "Skill pack deleted",
  "admin.skillPacks.deleteFailed": "Failed to delete skill pack",
  "admin.skillPacks.loadFailed": "Failed to load skill packs",
  "admin.skillPacks.empty": "No skill packs yet",
  "admin.skillPacks.zipHint": "Zip archive with SKILL.md at the root",
  "admin.skills.hint": "These are workflow-step skill definitions. For sandbox skill packs, use Skill Packs.",
```

In `frontend/src/locales/zh-CN.json`:

```json
  "admin.skillPacks": "Skill 包",
  "admin.skillPacks.upload": "上传 Skill 包",
  "admin.skillPacks.uploadSuccess": "Skill 包已上传",
  "admin.skillPacks.uploadFailed": "Skill 包上传失败",
  "admin.skillPacks.name": "名称",
  "admin.skillPacks.description": "描述",
  "admin.skillPacks.version": "版本",
  "admin.skillPacks.task": "绑定任务",
  "admin.skillPacks.enabled": "启用",
  "admin.skillPacks.updatedAt": "更新时间",
  "admin.skillPacks.deleteConfirm": "删除该 Skill 包？其任务将被停用。",
  "admin.skillPacks.deleteSuccess": "Skill 包已删除",
  "admin.skillPacks.deleteFailed": "删除 Skill 包失败",
  "admin.skillPacks.loadFailed": "加载 Skill 包失败",
  "admin.skillPacks.empty": "暂无 Skill 包",
  "admin.skillPacks.zipHint": "根目录包含 SKILL.md 的 zip 压缩包",
  "admin.skills.hint": "此处为工作流步骤的 Skill 定义；sandbox 指令包请使用 Skill 包页。",
```

- [ ] **Step 2: Create the admin page**

Create `frontend/src/pages/admin/SkillPacks.tsx`:

```tsx
import { DeleteOutlined, UploadOutlined } from '@ant-design/icons';
import { Button, Popconfirm, Switch, Table, Tag, Typography, Upload, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import PageContainer from '../../components/library/PageContainer';
import { formatDateTime } from '../../components/library/library-utils';
import apiClient from '../../services/api-client';

interface SkillPack {
  id: string;
  version: number;
  name: string;
  description: string;
  is_enabled: boolean;
  task_id: string;
  updated_at: string | null;
}

export default function SkillPacksAdmin() {
  const { t, i18n } = useTranslation();
  const [packs, setPacks] = useState<SkillPack[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);

  const loadPacks = () => {
    setLoading(true);
    apiClient.get('/admin/skill-packs')
      .then((response) => setPacks(response.data))
      .catch(() => message.error(t('admin.skillPacks.loadFailed')))
      .finally(() => setLoading(false));
  };

  useEffect(loadPacks, []);

  const uploadPack = async (file: File) => {
    setUploading(true);
    const formData = new FormData();
    formData.append('file', file);
    try {
      await apiClient.post('/admin/skill-packs', formData, { timeout: 60000 });
      message.success(t('admin.skillPacks.uploadSuccess'));
      loadPacks();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detail || t('admin.skillPacks.uploadFailed'));
    } finally {
      setUploading(false);
    }
    return false;
  };

  const toggleEnabled = async (pack: SkillPack, enabled: boolean) => {
    try {
      await apiClient.patch(`/admin/skill-packs/${pack.id}`, { is_enabled: enabled });
      loadPacks();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detail || t('admin.skillPacks.uploadFailed'));
    }
  };

  const deletePack = async (pack: SkillPack) => {
    try {
      await apiClient.delete(`/admin/skill-packs/${pack.id}`);
      message.success(t('admin.skillPacks.deleteSuccess'));
      loadPacks();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detail || t('admin.skillPacks.deleteFailed'));
    }
  };

  const columns: ColumnsType<SkillPack> = [
    {
      title: t('admin.skillPacks.name'),
      dataIndex: 'name',
      render: (value: string, record) => (
        <div>
          <Typography.Text strong>{value}</Typography.Text>
          <Typography.Text type="secondary" style={{ display: 'block', fontSize: 12 }}>
            {record.id}
          </Typography.Text>
        </div>
      ),
    },
    {
      title: t('admin.skillPacks.description'),
      dataIndex: 'description',
      ellipsis: true,
    },
    {
      title: t('admin.skillPacks.version'),
      dataIndex: 'version',
      width: 90,
      render: (value: number) => <Tag>{`v${value}`}</Tag>,
    },
    {
      title: t('admin.skillPacks.task'),
      dataIndex: 'task_id',
      width: 220,
      render: (value: string) => <Typography.Text code>{value}</Typography.Text>,
    },
    {
      title: t('admin.skillPacks.enabled'),
      dataIndex: 'is_enabled',
      width: 100,
      render: (value: boolean, record) => (
        <Switch checked={value} onChange={(checked) => toggleEnabled(record, checked)} />
      ),
    },
    {
      title: t('admin.skillPacks.updatedAt'),
      dataIndex: 'updated_at',
      width: 170,
      render: (value: string | null) => (value ? formatDateTime(value, i18n.language) : '-'),
    },
    {
      title: t('common.actions'),
      width: 90,
      render: (_, record) => (
        <Popconfirm
          title={t('admin.skillPacks.deleteConfirm')}
          okButtonProps={{ danger: true }}
          onConfirm={() => deletePack(record)}
        >
          <Button type="text" size="small" danger icon={<DeleteOutlined />} />
        </Popconfirm>
      ),
    },
  ];

  return (
    <PageContainer
      title={t('admin.skillPacks')}
      extra={(
        <Upload beforeUpload={uploadPack} showUploadList={false} accept=".zip">
          <Button type="primary" icon={<UploadOutlined />} loading={uploading}>
            {t('admin.skillPacks.upload')}
          </Button>
        </Upload>
      )}
    >
      <Typography.Paragraph type="secondary">
        {t('admin.skillPacks.zipHint')}
      </Typography.Paragraph>
      <Table
        rowKey="id"
        dataSource={packs}
        columns={columns}
        loading={loading}
        size="middle"
        pagination={{ pageSize: 10, hideOnSinglePage: true, showSizeChanger: false }}
        locale={{ emptyText: t('admin.skillPacks.empty') }}
      />
    </PageContainer>
  );
}
```

- [ ] **Step 3: Add the Skills-page clarification note**

In `frontend/src/pages/admin/Skills.tsx`, find the page container/description area and add a secondary paragraph under the title (use the existing description prop or a `Typography.Paragraph` at the top of the children, matching the file's current structure):

```tsx
<Typography.Paragraph type="secondary">
  {t('admin.skills.hint')}
</Typography.Paragraph>
```

- [ ] **Step 4: Register route and nav**

In `frontend/src/App.tsx`:

- Add the import beside the other admin imports (line 22):

```tsx
import SkillPacksAdmin from './pages/admin/SkillPacks';
```

- Add the nav item after the skills entry (line 69):

```tsx
            { key: '/admin/skill-packs', label: t('admin.skillPacks') },
```

- Add the route after the skills route (line 170):

```tsx
          <Route path="/admin/skill-packs" element={<SkillPacksAdmin />} />
```

- [ ] **Step 5: Build the frontend**

Run: `cd frontend && npm run build`
Expected: PASS.

- [ ] **Step 6: Commit the admin page**

```bash
git add frontend/src/pages/admin/SkillPacks.tsx frontend/src/App.tsx frontend/src/pages/admin/Skills.tsx frontend/src/locales/en-US.json frontend/src/locales/zh-CN.json
git commit -m "feat: add admin skill pack management page"
```

### Task 8: Full verification

**Files:**
- Modify: no source files expected

- [ ] **Step 1: Run all affected backend tests**

Run: `backend/.venv/bin/pytest tests/test_skill_packs.py tests/test_orchestration_runs.py tests/test_tasks_api.py tests/test_admin.py -q -p no:cacheprovider`
Expected: PASS. (Note: pytest processes in this repo sometimes hang on exit while holding `tmp/test.db`; if a run hangs, kill stale pytest processes with `pkill -9 -f "backend/.venv.*pytest"` and rerun.)

- [ ] **Step 2: Run the production frontend build**

Run: `cd frontend && npm run build`
Expected: PASS.

- [ ] **Step 3: Run changed-file pre-commit checks**

Run: `backend/.venv/bin/pre-commit run --files backend/app/models/skill_pack.py backend/app/models/__init__.py backend/app/models/task_definition.py backend/app/schemas/skill_pack.py backend/app/schemas/task.py backend/app/schemas/orchestration.py backend/app/core/config.py backend/alembic/versions/r9s0t1u2v3w4_add_skill_packs.py backend/app/services/skill_pack_service.py backend/app/services/orchestration_service.py backend/app/api/admin.py backend/app/api/orchestration.py tests/test_skill_packs.py frontend/src/types/task.ts frontend/src/pages/Session.tsx frontend/src/pages/admin/SkillPacks.tsx frontend/src/pages/admin/Skills.tsx frontend/src/App.tsx frontend/src/locales/en-US.json frontend/src/locales/zh-CN.json`
Expected: PASS.

- [ ] **Step 4: Smoke the docker-compose wiring**

Verify `docker-compose.yml` mounts `./codex-workspace` into both backend (`/codex-workspace`) and sandbox (`/workspace`) — it already does (lines 62 and 89), so `skill-runs/{run_id}` needs no compose change. Confirm `OPENCOLAB_CODEX_RUNTIME_WORKSPACE_DIR`/`OPENCOLAB_CODEX_RUNTIME_SANDBOX_WORKSPACE_DIR` are set in the environment used for the sandbox run (same variables the workflow path uses).

## Self-review

- **Spec coverage:** Skill-pack format/limits → Task 2 (`_validate_members`, `_parse_skill_md`). Model/storage → Task 1. Admin API incl. versions/patch/delete + task binding sync → Tasks 2–3. Workspace prep with permission-filtered parsed-text export + manifest → Task 4. Execution via OrchestrationRun + thin prompt + sandbox cwd → Task 5 (route generalizes the existing orchestration router with a `skill-pack` kind, per the spec's default choice; `project-qa` route untouched). Frontend admin page + Skills hint → Task 7. Session routing + task type → Task 6. Error mappings (400/403/409/502) → Tasks 3 and 5. Privacy (no PDFs, permission-filtered sources) → Task 4 (`collect_project_source_ids`).
- **Placeholder scan:** No TBD/deferred markers; every code step contains complete code.
- **Type consistency:** `store_skill_pack_zip(content, *, db, created_by)` used identically in tests and admin API. `prepare_skill_run_workspace(*, db, run_id, pack, session, user)` matches Task 5 usage. `SkillPackResponse.task_id` is a `@computed_field` serialized automatically; the frontend `SkillPack` interface reads `task_id`. `SKILL_PACK_WORKFLOW_SENTINEL = "skill-pack"` is asserted in Task 2 tests. Frontend branch checks `task.skill_pack_id`, which Task 1 adds to both backend schema and Task 6 frontend type. Tests resolve the session workspace via an explicit `Workspace` query (async SQLAlchemy forbids lazy-loading `user.workspace`), and workspace/run tests monkeypatch `app.services.research_context.can_user_use_source_in_agent` with `_always_authorized` because the production permission filter requires a sealed revision plus access policy that unit tests do not set up.
