# Lab Library Permissions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the v1 laboratory library layer so project materials, uploaded sources, generated outputs, and research memory can be published, withdrawn, referenced by projects, and used by RAG without breaking project permissions.

**Architecture:** Add a thin `ResearchAsset` index layer over existing `Source` and `ResearchObject` rows instead of replacing them. Add `ProjectAssetLink` for project context membership and use asset visibility plus project links to decide read/RAG access. Keep `Source.type = "group"` as collection-only organization, not permission.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, Alembic, Pydantic v2, React, Ant Design, React Query-style existing API calls, pytest, Vite.

---

## File Structure

- Create `backend/app/models/research_asset.py`
  - Owns `ResearchAsset` and `ProjectAssetLink`.
  - Does not store raw file content; it points to `Source` or `ResearchObject`.
- Create `backend/alembic/versions/g7a8b9c0d1e2_add_research_assets.py`
  - Creates `research_assets` and `project_asset_links`.
- Create `backend/app/schemas/research_asset.py`
  - Request/response models for library listing, publish, withdraw, link to project, and project material views.
- Create `backend/app/services/research_asset_service.py`
  - Centralizes visibility checks, source/research-object materialization, publish/withdraw rules, and project-link rules.
- Create `backend/app/api/research_assets.py`
  - REST endpoints for `/api/v1/library`, `/api/v1/projects/{project_id}/assets`, publish/withdraw/link operations.
- Modify `backend/app/models/__init__.py`
  - Export new models.
- Modify `backend/app/main.py`
  - Register `research_assets` router.
- Modify `backend/app/api/sources.py`
  - Ensure uploaded project/session sources are materialized into `ResearchAsset`.
- Modify `backend/app/api/research_objects.py`, `backend/app/api/agents.py`, `backend/app/api/workflows.py`
  - Materialize saved research memory and task/agent outputs as project-scoped assets.
- Modify `backend/app/services/research_context.py`, `backend/app/api/workflows.py`, `backend/app/api/agents.py`, `backend/app/api/websocket.py`
  - Prefer project asset links as the durable project context source.
- Create `tests/test_research_assets.py`
  - Asset visibility, publishing, withdraw, project links, and RAG context behavior.
- Create `frontend/src/types/research-asset.ts`
  - Shared frontend types.
- Create `frontend/src/pages/Library.tsx`
  - Lab library page.
- Create `frontend/src/pages/ProjectAssets.tsx`
  - Project materials page.
- Modify `frontend/src/App.tsx`
  - Add `/library` and `/projects/:projectId/assets`.
- Modify `frontend/src/pages/Home.tsx`
  - Add project "资料" action.
- Modify `frontend/src/pages/Session.tsx` and `frontend/src/pages/TaskWorkspace.tsx`
  - Add "save as project material" / "publish to library" entry points where existing data is already available.
- Modify `frontend/src/locales/zh-CN.json` and `frontend/src/locales/en-US.json`
  - Add user-facing text.

## Decisions Locked For v1

- Do not introduce Team.
- Do not introduce multi-lab tables.
- Treat active system users as lab members for `lab_public` visibility in v1; admin/PI can see `lab_private`.
- Use `ResearchAsset.visibility_scope`:
  - `private`: owner only.
  - `project`: visible through `ProjectAssetLink`.
  - `lab_private`: PI/Admin visible globally; project members visible only after project link.
  - `lab_public`: all authenticated users can discover and cite; existing project links survive withdrawal.
- Use `ResearchAsset.publication_status`:
  - `active`: normal.
  - `withdrawn`: hidden from ordinary lab discovery, still visible to PI/Admin and existing linked projects with a warning.
- A project link grants project members read access to that asset in that project.
- Research memory published to lab cannot be edited through existing edit APIs; revision creates a new asset.
- Collections organize assets/sources only and do not grant permission.

---

### Task 1: Add Research Asset Models And Migration

**Files:**
- Create: `backend/app/models/research_asset.py`
- Create: `backend/alembic/versions/g7a8b9c0d1e2_add_research_assets.py`
- Modify: `backend/app/models/__init__.py`
- Test: `tests/test_research_assets.py`

- [ ] **Step 1: Write failing model registration test**

Add to `tests/test_research_assets.py`:

```python
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base

pytestmark = pytest.mark.asyncio


async def test_research_asset_tables_are_registered(db: AsyncSession):
    result = await db.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
    table_names = {name for (name,) in result.all()}

    assert "research_assets" in Base.metadata.tables
    assert "project_asset_links" in Base.metadata.tables
    assert "research_assets" in table_names
    assert "project_asset_links" in table_names
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
backend/.venv/bin/python -m pytest tests/test_research_assets.py::test_research_asset_tables_are_registered -q
```

Expected: FAIL because `research_assets` is not registered.

- [ ] **Step 3: Create SQLAlchemy models**

Create `backend/app/models/research_asset.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ResearchAsset(Base):
    __tablename__ = "research_assets"
    __table_args__ = (
        UniqueConstraint("source_id", name="uq_research_assets_source_id"),
        UniqueConstraint("research_object_id", name="uq_research_assets_research_object_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    asset_type: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sources.id", ondelete="CASCADE"), nullable=True, index=True
    )
    research_object_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("research_objects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    owner_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    origin_project_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    origin_session_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    visibility_scope: Mapped[str] = mapped_column(String(32), default="project", server_default="project", index=True)
    publication_status: Mapped[str] = mapped_column(String(32), default="active", server_default="active", index=True)
    published_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    withdrawal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    project_links: Mapped[list["ProjectAssetLink"]] = relationship(
        back_populates="asset", cascade="all, delete-orphan", passive_deletes=True
    )


class ProjectAssetLink(Base):
    __tablename__ = "project_asset_links"
    __table_args__ = (
        UniqueConstraint("project_id", "asset_id", name="uq_project_asset_link"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_assets.id", ondelete="CASCADE"), index=True
    )
    link_type: Mapped[str] = mapped_column(String(32), default="reference", server_default="reference", index=True)
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    asset: Mapped["ResearchAsset"] = relationship(back_populates="project_links")
```

Modify `backend/app/models/__init__.py` to import and export:

```python
from app.models.research_asset import ProjectAssetLink, ResearchAsset
```

and add both names to `__all__`.

- [ ] **Step 4: Create Alembic migration**

Create `backend/alembic/versions/g7a8b9c0d1e2_add_research_assets.py`:

```python
"""add research assets

Revision ID: g7a8b9c0d1e2
Revises: f3b1a7c9d2e4
Create Date: 2026-07-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "g7a8b9c0d1e2"
down_revision: Union[str, None] = "f3b1a7c9d2e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "research_assets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("asset_type", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_id", sa.String(length=36), nullable=True),
        sa.Column("research_object_id", sa.String(length=36), nullable=True),
        sa.Column("owner_id", sa.String(length=36), nullable=True),
        sa.Column("origin_project_id", sa.String(length=36), nullable=True),
        sa.Column("origin_session_id", sa.String(length=36), nullable=True),
        sa.Column("visibility_scope", sa.String(length=32), server_default="project", nullable=False),
        sa.Column("publication_status", sa.String(length=32), server_default="active", nullable=False),
        sa.Column("published_by", sa.String(length=36), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawal_reason", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["origin_project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["origin_session_id"], ["sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["published_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["research_object_id"], ["research_objects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("research_object_id", name="uq_research_assets_research_object_id"),
        sa.UniqueConstraint("source_id", name="uq_research_assets_source_id"),
    )
    for column in [
        "asset_type",
        "source_id",
        "research_object_id",
        "owner_id",
        "origin_project_id",
        "origin_session_id",
        "visibility_scope",
        "publication_status",
        "published_by",
    ]:
        op.create_index(op.f(f"ix_research_assets_{column}"), "research_assets", [column], unique=False)

    op.create_table(
        "project_asset_links",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("asset_id", sa.String(length=36), nullable=False),
        sa.Column("link_type", sa.String(length=32), server_default="reference", nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["research_assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "asset_id", name="uq_project_asset_link"),
    )
    for column in ["project_id", "asset_id", "link_type", "created_by"]:
        op.create_index(op.f(f"ix_project_asset_links_{column}"), "project_asset_links", [column], unique=False)


def downgrade() -> None:
    for column in ["project_id", "asset_id", "link_type", "created_by"]:
        op.drop_index(op.f(f"ix_project_asset_links_{column}"), table_name="project_asset_links")
    op.drop_table("project_asset_links")

    for column in [
        "asset_type",
        "source_id",
        "research_object_id",
        "owner_id",
        "origin_project_id",
        "origin_session_id",
        "visibility_scope",
        "publication_status",
        "published_by",
    ]:
        op.drop_index(op.f(f"ix_research_assets_{column}"), table_name="research_assets")
    op.drop_table("research_assets")
```

- [ ] **Step 5: Run test to verify it passes**

Run:

```bash
backend/.venv/bin/python -m pytest tests/test_research_assets.py::test_research_asset_tables_are_registered -q
```

Expected: PASS.

---

### Task 2: Add Asset Schemas And Service Rules

**Files:**
- Create: `backend/app/schemas/research_asset.py`
- Create: `backend/app/services/research_asset_service.py`
- Test: `tests/test_research_assets.py`

- [ ] **Step 1: Add failing service tests**

Append to `tests/test_research_assets.py`:

```python
from app.models.project import Project, ResearcherProject
from app.models.research_asset import ResearchAsset
from app.models.source import Source, WorkspaceSource
from app.models.user import User, Workspace
from app.services.research_asset_service import (
    can_user_read_asset,
    link_asset_to_project,
    materialize_source_asset,
    publish_asset,
    withdraw_asset,
)


async def _workspace_id(db: AsyncSession, user_id: str) -> str:
    return await db.scalar(select(Workspace.id).where(Workspace.researcher_id == user_id))


async def test_project_asset_is_visible_to_project_member(db: AsyncSession, researcher_user: User):
    project = Project(name="P", description=None)
    source = Source(type="file", name="paper.pdf", owner_id=researcher_user.id, processing_state="ready")
    db.add_all([project, source])
    await db.flush()
    db.add(ResearcherProject(project_id=project.id, researcher_id=researcher_user.id, role="owner"))
    db.add(WorkspaceSource(workspace_id=await _workspace_id(db, researcher_user.id), source_id=source.id))
    await db.flush()

    asset = await materialize_source_asset(
        db=db,
        source=source,
        owner_id=researcher_user.id,
        origin_project_id=project.id,
        origin_session_id=None,
        visibility_scope="project",
        link_type="source",
    )
    await db.flush()

    assert await can_user_read_asset(db, researcher_user, asset) is True


async def test_lab_private_is_hidden_until_linked(db: AsyncSession, admin_user: User, researcher_user: User):
    project = Project(name="P", description=None)
    asset = ResearchAsset(
        asset_type="uploaded_file",
        title="private library paper",
        owner_id=admin_user.id,
        visibility_scope="lab_private",
    )
    db.add_all([project, asset])
    await db.flush()
    db.add(ResearcherProject(project_id=project.id, researcher_id=researcher_user.id, role="member"))
    await db.flush()

    assert await can_user_read_asset(db, researcher_user, asset) is False
    await link_asset_to_project(db=db, asset=asset, project_id=project.id, created_by=admin_user.id, link_type="reference")
    await db.flush()
    assert await can_user_read_asset(db, researcher_user, asset) is True


async def test_withdraw_public_asset_hides_lab_discovery_but_keeps_project_link(
    db: AsyncSession, admin_user: User, researcher_user: User
):
    project = Project(name="P", description=None)
    asset = ResearchAsset(
        asset_type="uploaded_file",
        title="public paper",
        owner_id=admin_user.id,
        visibility_scope="lab_public",
    )
    db.add_all([project, asset])
    await db.flush()
    db.add(ResearcherProject(project_id=project.id, researcher_id=researcher_user.id, role="member"))
    await link_asset_to_project(db=db, asset=asset, project_id=project.id, created_by=admin_user.id, link_type="reference")
    await withdraw_asset(db=db, asset=asset, user=admin_user, reason="outdated")
    await db.flush()

    assert asset.publication_status == "withdrawn"
    assert await can_user_read_asset(db, researcher_user, asset) is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
backend/.venv/bin/python -m pytest tests/test_research_assets.py -q
```

Expected: FAIL because service and schema files are missing.

- [ ] **Step 3: Create schemas**

Create `backend/app/schemas/research_asset.py`:

```python
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

VisibilityScope = Literal["private", "project", "lab_private", "lab_public"]
PublicationStatus = Literal["active", "withdrawn"]


class ResearchAssetResponse(BaseModel):
    id: str
    asset_type: str
    title: str
    description: str | None = None
    source_id: str | None = None
    research_object_id: str | None = None
    owner_id: str | None = None
    origin_project_id: str | None = None
    origin_session_id: str | None = None
    visibility_scope: str
    publication_status: str
    published_by: str | None = None
    published_at: datetime | None = None
    withdrawn_at: datetime | None = None
    withdrawal_reason: str | None = None
    metadata_json: dict
    created_at: datetime
    updated_at: datetime
    is_linked_to_project: bool = False
    can_publish: bool = False
    can_withdraw: bool = False
    withdrawn_warning: str | None = None

    model_config = {"from_attributes": True}


class PublishAssetRequest(BaseModel):
    visibility_scope: Literal["lab_private", "lab_public"]
    description: str | None = Field(default=None, max_length=2000)
    publication_note: str | None = Field(default=None, max_length=2000)


class WithdrawAssetRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


class LinkAssetToProjectRequest(BaseModel):
    project_id: str
    link_type: str = "reference"


class SaveGeneratedAssetRequest(BaseModel):
    project_id: str
    title: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1)
    asset_type: str = "generated_doc"
    metadata_json: dict = Field(default_factory=dict)
```

- [ ] **Step 4: Create service**

Create `backend/app/services/research_asset_service.py` with these exact public functions:

```python
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ROLE_ADMIN, ROLE_PI
from app.models.project import Project, ResearcherProject
from app.models.research_asset import ProjectAssetLink, ResearchAsset
from app.models.research_object import ResearchObject
from app.models.source import Source
from app.models.user import User

PRIVILEGED_ROLES = {ROLE_ADMIN, ROLE_PI}
PROJECT_LINK_TYPES = {"source", "output", "memory", "reference"}


def is_privileged(user: User) -> bool:
    return user.role in PRIVILEGED_ROLES


async def get_project_membership(db: AsyncSession, project_id: str, user_id: str) -> ResearcherProject | None:
    return await db.scalar(
        select(ResearcherProject).where(
            ResearcherProject.project_id == project_id,
            ResearcherProject.researcher_id == user_id,
        )
    )


async def can_user_read_asset(db: AsyncSession, user: User, asset: ResearchAsset) -> bool:
    if is_privileged(user):
        return True
    if asset.owner_id == user.id and asset.visibility_scope == "private":
        return True
    if asset.visibility_scope == "lab_public" and asset.publication_status == "active":
        return True
    linked_project_ids = await db.scalars(
        select(ProjectAssetLink.project_id).where(ProjectAssetLink.asset_id == asset.id)
    )
    for project_id in linked_project_ids.all():
        if await get_project_membership(db, project_id, user.id) is not None:
            return True
    return False


async def can_user_manage_asset(db: AsyncSession, user: User, asset: ResearchAsset) -> bool:
    if is_privileged(user):
        return True
    if asset.owner_id == user.id:
        return True
    if asset.origin_project_id:
        membership = await get_project_membership(db, asset.origin_project_id, user.id)
        return membership is not None and membership.role == "owner"
    return False


def source_asset_type(source: Source) -> str:
    if source.type == "file":
        return "uploaded_file"
    if source.type == "group":
        return "collection"
    if source.type == "note":
        return "generated_doc"
    return "external_reference"


async def materialize_source_asset(
    *,
    db: AsyncSession,
    source: Source,
    owner_id: str | None,
    origin_project_id: str | None,
    origin_session_id: str | None,
    visibility_scope: str,
    link_type: str,
) -> ResearchAsset:
    existing = await db.scalar(select(ResearchAsset).where(ResearchAsset.source_id == source.id))
    if existing is not None:
        asset = existing
    else:
        asset = ResearchAsset(
            asset_type=source_asset_type(source),
            title=source.name,
            source_id=source.id,
            owner_id=owner_id,
            origin_project_id=origin_project_id,
            origin_session_id=origin_session_id,
            visibility_scope=visibility_scope,
            metadata_json={"source_type": source.type},
        )
        db.add(asset)
        await db.flush()
    if origin_project_id:
        await link_asset_to_project(
            db=db,
            asset=asset,
            project_id=origin_project_id,
            created_by=owner_id,
            link_type=link_type,
        )
    return asset


async def materialize_research_object_asset(
    *,
    db: AsyncSession,
    research_object: ResearchObject,
    owner_id: str | None,
    origin_project_id: str | None,
    origin_session_id: str | None,
    visibility_scope: str,
    link_type: str,
) -> ResearchAsset:
    existing = await db.scalar(
        select(ResearchAsset).where(ResearchAsset.research_object_id == research_object.id)
    )
    if existing is not None:
        asset = existing
    else:
        asset = ResearchAsset(
            asset_type="research_memory",
            title=research_object.title or research_object.type,
            description=None,
            research_object_id=research_object.id,
            owner_id=owner_id,
            origin_project_id=origin_project_id,
            origin_session_id=origin_session_id,
            visibility_scope=visibility_scope,
            metadata_json={"research_object_type": research_object.type},
        )
        db.add(asset)
        await db.flush()
    if origin_project_id:
        await link_asset_to_project(
            db=db,
            asset=asset,
            project_id=origin_project_id,
            created_by=owner_id,
            link_type=link_type,
        )
    return asset


async def link_asset_to_project(
    *,
    db: AsyncSession,
    asset: ResearchAsset,
    project_id: str,
    created_by: str | None,
    link_type: str,
) -> ProjectAssetLink:
    if link_type not in PROJECT_LINK_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid link_type")
    project_exists = await db.scalar(select(Project.id).where(Project.id == project_id))
    if project_exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    existing = await db.scalar(
        select(ProjectAssetLink).where(
            ProjectAssetLink.project_id == project_id,
            ProjectAssetLink.asset_id == asset.id,
        )
    )
    if existing is not None:
        return existing
    link = ProjectAssetLink(
        project_id=project_id,
        asset_id=asset.id,
        created_by=created_by,
        link_type=link_type,
    )
    db.add(link)
    await db.flush()
    return link


async def publish_asset(
    *,
    db: AsyncSession,
    asset: ResearchAsset,
    user: User,
    visibility_scope: str,
    description: str | None,
    publication_note: str | None,
) -> ResearchAsset:
    if visibility_scope not in {"lab_private", "lab_public"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid visibility_scope")
    if not await can_user_manage_asset(db, user, asset):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    asset.visibility_scope = visibility_scope
    asset.publication_status = "active"
    asset.description = description if description is not None else asset.description
    asset.published_by = user.id
    asset.published_at = datetime.now(UTC)
    asset.withdrawn_at = None
    asset.withdrawal_reason = None
    asset.metadata_json = {
        **(asset.metadata_json or {}),
        "publication_note": publication_note,
    }
    await db.flush()
    return asset


async def withdraw_asset(
    *,
    db: AsyncSession,
    asset: ResearchAsset,
    user: User,
    reason: str | None,
) -> ResearchAsset:
    if not await can_user_manage_asset(db, user, asset):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    asset.publication_status = "withdrawn"
    asset.withdrawn_at = datetime.now(UTC)
    asset.withdrawal_reason = reason
    await db.flush()
    return asset
```

- [ ] **Step 5: Run service tests**

Run:

```bash
backend/.venv/bin/python -m pytest tests/test_research_assets.py -q
```

Expected: PASS.

---

### Task 3: Add Research Asset API

**Files:**
- Create: `backend/app/api/research_assets.py`
- Modify: `backend/app/main.py`
- Test: `tests/test_research_assets.py`

- [ ] **Step 1: Add failing API tests**

Append to `tests/test_research_assets.py`:

```python
async def test_library_lists_public_assets(client, auth_headers, researcher_headers, admin_user, db):
    asset = ResearchAsset(
        asset_type="uploaded_file",
        title="public paper",
        owner_id=admin_user.id,
        visibility_scope="lab_public",
    )
    db.add(asset)
    await db.commit()

    response = await client.get("/api/v1/library/assets", headers=researcher_headers)
    assert response.status_code == 200
    assert any(item["id"] == asset.id for item in response.json())


async def test_project_owner_can_publish_project_asset(client, auth_headers, admin_user, db):
    project = Project(name="P", description=None)
    asset = ResearchAsset(asset_type="uploaded_file", title="draft", owner_id=admin_user.id, visibility_scope="project")
    db.add_all([project, asset])
    await db.flush()
    db.add(ResearcherProject(project_id=project.id, researcher_id=admin_user.id, role="owner"))
    await link_asset_to_project(db=db, asset=asset, project_id=project.id, created_by=admin_user.id, link_type="source")
    await db.commit()

    response = await client.post(
        f"/api/v1/library/assets/{asset.id}/publish",
        json={"visibility_scope": "lab_public", "description": "Published", "publication_note": "ready"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["visibility_scope"] == "lab_public"


async def test_project_assets_lists_linked_assets(client, auth_headers, admin_user, db):
    project = Project(name="P", description=None)
    asset = ResearchAsset(asset_type="uploaded_file", title="linked", owner_id=admin_user.id, visibility_scope="project")
    db.add_all([project, asset])
    await db.flush()
    db.add(ResearcherProject(project_id=project.id, researcher_id=admin_user.id, role="owner"))
    await link_asset_to_project(db=db, asset=asset, project_id=project.id, created_by=admin_user.id, link_type="source")
    await db.commit()

    response = await client.get(f"/api/v1/projects/{project.id}/assets", headers=auth_headers)
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [asset.id]
```

- [ ] **Step 2: Create API router**

Create `backend/app/api/research_assets.py`:

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.projects import _get_project_for_user, _user_can_manage_project
from app.core.constants import ROLE_ADMIN, ROLE_PI
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.research_asset import ProjectAssetLink, ResearchAsset
from app.models.user import User
from app.schemas.research_asset import (
    LinkAssetToProjectRequest,
    PublishAssetRequest,
    ResearchAssetResponse,
    WithdrawAssetRequest,
)
from app.services.research_asset_service import (
    can_user_manage_asset,
    can_user_read_asset,
    link_asset_to_project,
    publish_asset,
    withdraw_asset,
)

router = APIRouter(tags=["research-assets"])


def _response(asset: ResearchAsset, *, linked: bool = False) -> ResearchAssetResponse:
    withdrawn_warning = None
    if asset.publication_status == "withdrawn":
        withdrawn_warning = "This asset has been withdrawn from public lab discovery."
    return ResearchAssetResponse.model_validate(
        {
            **ResearchAssetResponse.model_validate(asset).model_dump(),
            "is_linked_to_project": linked,
            "withdrawn_warning": withdrawn_warning,
        }
    )


async def _get_asset_or_404(db: AsyncSession, asset_id: str) -> ResearchAsset:
    asset = await db.scalar(select(ResearchAsset).where(ResearchAsset.id == asset_id))
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset


@router.get("/library/assets", response_model=list[ResearchAssetResponse])
async def list_library_assets(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.role in {ROLE_ADMIN, ROLE_PI}:
        stmt = select(ResearchAsset).where(
            ResearchAsset.visibility_scope.in_(["lab_private", "lab_public"])
        )
    else:
        stmt = select(ResearchAsset).where(
            ResearchAsset.visibility_scope == "lab_public",
            ResearchAsset.publication_status == "active",
        )
    stmt = stmt.order_by(ResearchAsset.updated_at.desc(), ResearchAsset.id.desc())
    assets = (await db.execute(stmt)).scalars().all()
    return [_response(asset) for asset in assets if await can_user_read_asset(db, user, asset)]


@router.get("/projects/{project_id}/assets", response_model=list[ResearchAssetResponse])
async def list_project_assets(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_for_user(project_id, user, db)
    stmt = (
        select(ResearchAsset)
        .join(ProjectAssetLink, ProjectAssetLink.asset_id == ResearchAsset.id)
        .where(ProjectAssetLink.project_id == project_id)
        .order_by(ProjectAssetLink.created_at.desc(), ProjectAssetLink.id.desc())
    )
    assets = (await db.execute(stmt)).scalars().all()
    return [_response(asset, linked=True) for asset in assets if await can_user_read_asset(db, user, asset)]


@router.post("/library/assets/{asset_id}/publish", response_model=ResearchAssetResponse)
async def publish_library_asset(
    asset_id: str,
    body: PublishAssetRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    asset = await _get_asset_or_404(db, asset_id)
    await publish_asset(
        db=db,
        asset=asset,
        user=user,
        visibility_scope=body.visibility_scope,
        description=body.description,
        publication_note=body.publication_note,
    )
    await db.commit()
    await db.refresh(asset)
    return _response(asset)


@router.post("/library/assets/{asset_id}/withdraw", response_model=ResearchAssetResponse)
async def withdraw_library_asset(
    asset_id: str,
    body: WithdrawAssetRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    asset = await _get_asset_or_404(db, asset_id)
    await withdraw_asset(db=db, asset=asset, user=user, reason=body.reason)
    await db.commit()
    await db.refresh(asset)
    return _response(asset)


@router.post("/library/assets/{asset_id}/link", response_model=ResearchAssetResponse)
async def link_library_asset(
    asset_id: str,
    body: LinkAssetToProjectRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    asset = await _get_asset_or_404(db, asset_id)
    if not await can_user_read_asset(db, user, asset):
        raise HTTPException(status_code=404, detail="Asset not found")
    project = await _get_project_for_user(body.project_id, user, db)
    if asset.visibility_scope == "lab_private" and user.role not in {ROLE_ADMIN, ROLE_PI}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only PI/Admin can link private lab assets")
    await link_asset_to_project(
        db=db,
        asset=asset,
        project_id=project.id,
        created_by=user.id,
        link_type=body.link_type,
    )
    await db.commit()
    await db.refresh(asset)
    return _response(asset, linked=True)
```

Modify `backend/app/main.py`:

```python
from app.api.research_assets import router as research_assets_router

app.include_router(research_assets_router, prefix=api)
```

- [ ] **Step 3: Run API tests**

Run:

```bash
backend/.venv/bin/python -m pytest tests/test_research_assets.py -q
```

Expected: PASS.

---

### Task 4: Materialize Existing Source And ResearchObject Writes

**Files:**
- Modify: `backend/app/api/sources.py`
- Modify: `backend/app/api/research_objects.py`
- Modify: `backend/app/api/agents.py`
- Modify: `backend/app/api/workflows.py`
- Test: `tests/test_research_assets.py`, existing source/research object tests.

- [ ] **Step 1: Add failing materialization tests**

Append to `tests/test_research_assets.py`:

```python
async def test_session_upload_creates_project_asset(client, auth_headers, admin_user, db):
    project = Project(name="P", description=None)
    db.add(project)
    await db.flush()
    db.add(ResearcherProject(project_id=project.id, researcher_id=admin_user.id, role="owner"))
    await db.commit()

    session_response = await client.post(
        "/api/v1/sessions",
        json={"title": "S", "project_id": project.id},
        headers=auth_headers,
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["id"]

    response = await client.post(
        f"/api/v1/sessions/{session_id}/sources",
        files={"file": ("paper.pdf", b"%PDF-1.4\n", "application/pdf")},
        headers=auth_headers,
    )
    assert response.status_code == 201

    assets = (await db.execute(select(ResearchAsset))).scalars().all()
    assert len(assets) == 1
    assert assets[0].visibility_scope == "project"
    assert assets[0].origin_project_id == project.id
```

- [ ] **Step 2: Update source creation paths**

In `backend/app/api/sources.py`, import:

```python
from app.services.research_asset_service import materialize_source_asset
```

After session upload creates and links a source, call:

```python
if session.project_id:
    await materialize_source_asset(
        db=db,
        source=source,
        owner_id=user.id,
        origin_project_id=session.project_id,
        origin_session_id=session.id,
        visibility_scope="project",
        link_type="source",
    )
```

For global upload without project, materialize as:

```python
await materialize_source_asset(
    db=db,
    source=source,
    owner_id=user.id,
    origin_project_id=None,
    origin_session_id=None,
    visibility_scope="private",
    link_type="source",
)
```

- [ ] **Step 3: Update research memory save paths**

In `backend/app/api/research_objects.py`, `backend/app/api/agents.py`, and `backend/app/api/workflows.py`, import:

```python
from app.services.research_asset_service import materialize_research_object_asset
```

After a `ResearchObject` is flushed, call:

```python
await materialize_research_object_asset(
    db=db,
    research_object=research_object,
    owner_id=user.id,
    origin_project_id=session.project_id,
    origin_session_id=session.id,
    visibility_scope="project",
    link_type="memory",
)
```

- [ ] **Step 4: Run tests**

Run:

```bash
backend/.venv/bin/python -m pytest tests/test_research_assets.py tests/test_source_extractions.py tests/test_agents_api.py tests/test_workflows_api.py -q
```

Expected: PASS. If pytest hangs after printing PASS, interrupt after recording the pass result.

---

### Task 5: Make RAG Project Context Use Project Asset Links

**Files:**
- Modify: `backend/app/services/research_context.py`
- Modify: `backend/app/api/workflows.py`
- Modify: `backend/app/api/agents.py`
- Modify: `backend/app/api/websocket.py`
- Test: `tests/test_research_assets.py`, `tests/test_workflows_api.py`

- [ ] **Step 1: Add failing RAG source collection test**

Append to `tests/test_research_assets.py`:

```python
from app.services.research_context import collect_project_source_ids


async def test_collect_project_source_ids_uses_project_asset_links(db: AsyncSession, admin_user: User):
    project = Project(name="P", description=None)
    source = Source(type="file", name="paper.pdf", owner_id=admin_user.id, processing_state="ready")
    db.add_all([project, source])
    await db.flush()
    asset = await materialize_source_asset(
        db=db,
        source=source,
        owner_id=admin_user.id,
        origin_project_id=project.id,
        origin_session_id=None,
        visibility_scope="project",
        link_type="source",
    )
    await db.flush()

    assert await collect_project_source_ids(db=db, project_id=project.id, user=admin_user) == [source.id]
```

- [ ] **Step 2: Implement project source collection**

In `backend/app/services/research_context.py`, add:

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research_asset import ProjectAssetLink, ResearchAsset
from app.models.user import User
from app.services.research_asset_service import can_user_read_asset


async def collect_project_source_ids(*, db: AsyncSession, project_id: str, user: User) -> list[str]:
    result = await db.execute(
        select(ResearchAsset)
        .join(ProjectAssetLink, ProjectAssetLink.asset_id == ResearchAsset.id)
        .where(ProjectAssetLink.project_id == project_id, ResearchAsset.source_id.is_not(None))
        .order_by(ProjectAssetLink.created_at.desc(), ProjectAssetLink.id.desc())
    )
    source_ids: list[str] = []
    for asset in result.scalars().all():
        if asset.source_id and await can_user_read_asset(db, user, asset):
            source_ids.append(asset.source_id)
    return source_ids
```

- [ ] **Step 3: Use this helper where project defaults are needed**

In workflow/task execution paths that currently infer session sources as project context, use:

```python
project_source_ids = await collect_project_source_ids(db=db, project_id=session.project_id, user=user)
```

Keep explicit session `source_ids` support unchanged.

- [ ] **Step 4: Run tests**

Run:

```bash
backend/.venv/bin/python -m pytest tests/test_research_assets.py tests/test_workflows_api.py -q
```

Expected: PASS.

---

### Task 6: Frontend Library And Project Materials Pages

**Files:**
- Create: `frontend/src/types/research-asset.ts`
- Create: `frontend/src/pages/Library.tsx`
- Create: `frontend/src/pages/ProjectAssets.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/pages/Home.tsx`
- Modify: `frontend/src/locales/zh-CN.json`
- Modify: `frontend/src/locales/en-US.json`

- [ ] **Step 1: Create frontend type file**

Create `frontend/src/types/research-asset.ts`:

```ts
export interface ResearchAsset {
  id: string;
  asset_type: string;
  title: string;
  description: string | null;
  source_id: string | null;
  research_object_id: string | null;
  owner_id: string | null;
  origin_project_id: string | null;
  origin_session_id: string | null;
  visibility_scope: 'private' | 'project' | 'lab_private' | 'lab_public';
  publication_status: 'active' | 'withdrawn';
  published_by: string | null;
  published_at: string | null;
  withdrawn_at: string | null;
  withdrawal_reason: string | null;
  metadata_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  is_linked_to_project: boolean;
  can_publish: boolean;
  can_withdraw: boolean;
  withdrawn_warning: string | null;
}
```

- [ ] **Step 2: Create lab library page**

Create `frontend/src/pages/Library.tsx`:

```tsx
import { LinkOutlined, StopOutlined } from '@ant-design/icons';
import { Button, Card, Space, Table, Tag, Typography, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import apiClient from '../services/api-client';
import type { ResearchAsset } from '../types/research-asset';

export default function Library() {
  const { t } = useTranslation();
  const [assets, setAssets] = useState<ResearchAsset[]>([]);
  const [loading, setLoading] = useState(false);

  const loadAssets = () => {
    setLoading(true);
    apiClient.get('/library/assets')
      .then((response) => setAssets(response.data))
      .catch(() => message.error(t('library.loadFailed')))
      .finally(() => setLoading(false));
  };

  useEffect(loadAssets, []);

  const columns: ColumnsType<ResearchAsset> = [
    {
      title: t('library.assetTitle'),
      dataIndex: 'title',
      render: (_, record) => (
        <Space direction="vertical" size={2}>
          <Typography.Text strong>{record.title}</Typography.Text>
          {record.description ? <Typography.Text type="secondary">{record.description}</Typography.Text> : null}
          {record.withdrawn_warning ? <Typography.Text type="warning">{record.withdrawn_warning}</Typography.Text> : null}
        </Space>
      ),
    },
    {
      title: t('library.visibility'),
      dataIndex: 'visibility_scope',
      render: (value: string) => <Tag>{t(`library.visibility.${value}`)}</Tag>,
    },
    {
      title: t('library.status'),
      dataIndex: 'publication_status',
      render: (value: string) => <Tag color={value === 'withdrawn' ? 'orange' : 'green'}>{t(`library.status.${value}`)}</Tag>,
    },
    {
      title: t('common.actions'),
      render: (_, record) => (
        <Button size="small" icon={<LinkOutlined />} disabled={record.publication_status === 'withdrawn'}>
          {t('library.linkToProject')}
        </Button>
      ),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <Card title={t('library.title')}>
        <Table rowKey="id" dataSource={assets} columns={columns} loading={loading} />
      </Card>
    </div>
  );
}
```

- [ ] **Step 3: Create project materials page**

Create `frontend/src/pages/ProjectAssets.tsx`:

```tsx
import { ArrowLeftOutlined } from '@ant-design/icons';
import { Button, Card, Empty, Space, Table, Tag, Typography, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';

import apiClient from '../services/api-client';
import type { ResearchAsset } from '../types/research-asset';

export default function ProjectAssets() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { projectId } = useParams();
  const [assets, setAssets] = useState<ResearchAsset[]>([]);
  const [loading, setLoading] = useState(false);

  const loadAssets = () => {
    if (!projectId) return;
    setLoading(true);
    apiClient.get(`/projects/${projectId}/assets`)
      .then((response) => setAssets(response.data))
      .catch(() => message.error(t('library.loadFailed')))
      .finally(() => setLoading(false));
  };

  useEffect(loadAssets, [projectId]);

  const columns: ColumnsType<ResearchAsset> = [
    {
      title: t('library.assetTitle'),
      dataIndex: 'title',
      render: (_, record) => (
        <Space direction="vertical" size={2}>
          <Typography.Text strong>{record.title}</Typography.Text>
          <Typography.Text type="secondary">{t(`library.assetType.${record.asset_type}`, record.asset_type)}</Typography.Text>
          {record.withdrawn_warning ? <Typography.Text type="warning">{record.withdrawn_warning}</Typography.Text> : null}
        </Space>
      ),
    },
    {
      title: t('library.visibility'),
      dataIndex: 'visibility_scope',
      render: (value: string) => <Tag>{t(`library.visibility.${value}`)}</Tag>,
    },
    {
      title: t('library.status'),
      dataIndex: 'publication_status',
      render: (value: string) => <Tag color={value === 'withdrawn' ? 'orange' : 'green'}>{t(`library.status.${value}`)}</Tag>,
    },
    {
      title: t('library.updatedAt'),
      dataIndex: 'updated_at',
      render: (value: string) => new Date(value).toLocaleString(),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <Card
        title={t('library.projectTitle')}
        extra={<Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/')}>{t('common.back')}</Button>}
      >
        <Table
          rowKey="id"
          dataSource={assets}
          columns={columns}
          loading={loading}
          locale={{ emptyText: <Empty description={t('library.projectEmpty')} /> }}
        />
      </Card>
    </div>
  );
}
```

- [ ] **Step 4: Wire routes and navigation**

Modify `frontend/src/App.tsx`:

```tsx
import Library from './pages/Library';
import ProjectAssets from './pages/ProjectAssets';

// nav items
{ key: '/library', icon: <FolderOutlined />, label: t('nav.library') }

// routes
<Route path="/library" element={<Library />} />
<Route path="/projects/:projectId/assets" element={<ProjectAssets />} />
```

Modify `frontend/src/pages/Home.tsx` project action list to link to:

```tsx
navigate(`/projects/${project.id}/assets`)
```

- [ ] **Step 5: Add i18n keys**

Add to `frontend/src/locales/zh-CN.json`:

```json
"nav.library": "资料库",
"library.title": "实验室资料库",
"library.projectTitle": "项目资料",
"library.assetTitle": "资料",
"library.visibility": "可见范围",
"library.status": "状态",
"library.linkToProject": "引用到项目",
"library.loadFailed": "加载资料失败",
"library.visibility.private": "私有",
"library.visibility.project": "项目",
"library.visibility.lab_private": "实验室私密",
"library.visibility.lab_public": "实验室公开",
"library.status.active": "可用",
"library.status.withdrawn": "已撤回公开"
```

Add to `frontend/src/locales/en-US.json`:

```json
"nav.library": "Library",
"library.title": "Lab Library",
"library.projectTitle": "Project Materials",
"library.assetTitle": "Material",
"library.visibility": "Visibility",
"library.status": "Status",
"library.updatedAt": "Updated",
"library.linkToProject": "Link to Project",
"library.loadFailed": "Failed to load materials",
"library.projectEmpty": "No project materials yet",
"library.visibility.private": "Private",
"library.visibility.project": "Project",
"library.visibility.lab_private": "Lab Private",
"library.visibility.lab_public": "Lab Public",
"library.status.active": "Active",
"library.status.withdrawn": "Withdrawn",
"library.assetType.uploaded_file": "Uploaded File",
"library.assetType.generated_doc": "Generated Document",
"library.assetType.research_memory": "Research Memory",
"library.assetType.report": "Report",
"library.assetType.dataset": "Dataset",
"library.assetType.protocol": "Protocol",
"library.assetType.external_reference": "External Reference",
"library.assetType.collection": "Collection"
```

- [ ] **Step 6: Run frontend build**

Run:

```bash
npm run build
```

from `frontend/`.

Expected: PASS.

---

### Task 7: Full Verification

**Files:**
- No new files.

- [ ] **Step 1: Run backend focused tests**

Run:

```bash
backend/.venv/bin/python -m pytest tests/test_research_assets.py tests/test_sharing.py tests/test_tasks_api.py tests/test_workflows_api.py -q
```

Expected: PASS. If pytest prints PASS and hangs during interpreter shutdown, interrupt and record the printed pass result.

- [ ] **Step 2: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 3: Smoke test Docker dev endpoints**

Run:

```bash
curl -sS http://127.0.0.1:8431/api/v1/health
```

Expected: healthy response from backend, or document if the local stack is not running.

- [ ] **Step 4: Manual browser smoke test**

Open:

```text
http://127.0.0.1:8430/library
```

Expected:

- Page renders.
- Table loads without API error.
- Existing lab-public assets appear when present.
- Withdrawn assets show warning for PI/Admin.

Open:

```text
http://127.0.0.1:8430/projects/<project_id>/assets
```

Expected:

- Page renders.
- Project-linked assets appear.
- Withdrawn linked assets remain visible with warning.

---

## Self-Review

**Spec coverage**

- Unified asset layer: Task 1 and Task 2.
- Project references: Task 1, Task 2, Task 3.
- Publish and withdraw: Task 2, Task 3.
- Research memory as assets: Task 4.
- Source/files as assets: Task 4.
- RAG permission behavior: Task 5.
- Lab library and project materials UI: Task 6.
- Collections remain non-permission: already implemented in the previous commit; tests remain in `tests/test_sharing.py`.

**Known v1 exclusions**

- No Team.
- No multi-lab.
- No full personal library page.
- No complex ACL UI.
- No binary export for generated docs.

**Ambiguity resolved for v1**

- Lab membership: all authenticated users are treated as lab members for `lab_public`; PI/Admin are privileged for `lab_private`.
- `lab_private` linked to a project becomes readable by that project's members.
- Project owner can publish project assets; PI/Admin can publish or withdraw any lab asset.
