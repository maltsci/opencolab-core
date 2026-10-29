# Lab Knowledge OS v1 Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Phase 0 authoritative domain, governance, security contracts, reversible migration, and real-question benchmark gate required by later Lab Knowledge OS phases.

**Architecture:** Add an independent `ResearchDirection` aggregate and explicit foreign-key association tables for people, projects, assets, and research objects. Add scoped steward assignments plus a generic suggestion/audit workflow, while keeping current PostgreSQL authorization authoritative for every resource-derived result.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, Alembic, Pydantic v2, PostgreSQL, SQLite test database, pytest, Ruff/pre-commit.

---

## Phase 0 Scope

This plan implements backend contracts and product/security baselines only. It does not implement People, Research, or Resources end-user pages, Activity Projection, unified Assistant UI, AI-generated suggestions, email/IM notifications, or usage analytics.

## File Map

### Create

- `backend/app/models/research_direction.py` — direction aggregate and direction-to-direction relation.
- `backend/app/models/research_direction_link.py` — explicit member, project, asset, and ResearchObject links.
- `backend/app/models/knowledge_governance.py` — group/direction steward assignments, suggestions, and immutable change events.
- `backend/app/schemas/research_direction.py` — direction and relation request/response contracts.
- `backend/app/schemas/knowledge_governance.py` — steward, suggestion, and decision contracts.
- `backend/app/services/research_direction_service.py` — lifecycle, list cursor, merge, and explicit association behavior.
- `backend/app/services/knowledge_governance_service.py` — authority checks, steward assignment, suggestion decisions, and audit writes.
- `backend/app/services/knowledge_access_service.py` — request-time asset authorization for future entity/RAG consumers.
- `backend/app/api/research_directions.py` — Phase 0 direction and association endpoints.
- `backend/app/api/knowledge_governance.py` — steward and suggestion endpoints.
- `backend/alembic/versions/w4x5y6z7a8b9_add_lab_knowledge_foundation.py` — reversible schema migration from `v3w4x5y6z7a8`.
- `tests/test_lab_knowledge_models.py` — ORM and database constraint tests.
- `tests/test_lab_knowledge_foundation_migration.py` — upgrade/downgrade and legacy-data preservation tests.
- `tests/test_research_directions.py` — lifecycle, pagination, merge, and association API tests.
- `tests/test_knowledge_governance.py` — steward and suggestion authority tests.
- `tests/test_knowledge_access_service.py` — current-permission and revocation contract tests.
- `docs/evaluations/lab-knowledge-os-v1-benchmark.schema.json` — machine-validatable benchmark format.
- `evaluation-data/lab-knowledge-os-v1-benchmark.zh-CN.json` — gitignored local dataset containing the 30 approved real questions.
- `docs/evaluations/lab-knowledge-os-v1-benchmark-manifest.json` — safe checksum and aggregate-count record without research content.
- `scripts/validate-lab-knowledge-benchmark.py` — offline benchmark schema/distribution validator.
- `docs/lab-knowledge-os-v1-security-contract.md` — request-time authorization and revocation threat model.
- `docs/lab-knowledge-os-v1-migration-runbook.md` — inventory, dry-run, conflict, rollback, and reconciliation procedure.

### Modify

- `backend/app/models/__init__.py` — import the new models so metadata and migrations see them.
- `backend/app/main.py` — register the two new API routers.
- `backend/app/services/rag_service.py` — route source/asset authorization through the shared request-time access service without changing retrieval scores.
- `tests/test_rag_service.py` — preserve query-time authorization after revocation.
- `.gitignore` — exclude the local evaluation dataset while retaining its safe manifest.
- `docs/superpowers/specs/2026-08-07-lab-knowledge-os-v1-prd.zh-CN.md` — link the approved Phase 0 contracts only if implementation reveals a genuine contradiction; do not silently change scope.

## Domain Contract

Use these constants in schema/service modules; do not encode them as PostgreSQL enums because later versions need additive values without enum migrations:

```python
DIRECTION_STATUSES = ("active", "archived", "merged")
DIRECTION_RELATION_TYPE = "related"
MEMBER_DIRECTION_ROLES = ("lead", "contributor")
RESEARCH_OBJECT_DIRECTION_TYPES = ("belongs_to", "informs")
SUGGESTION_STATUSES = ("pending", "approved", "rejected")
SUGGESTION_ACTIONS = ("create", "update", "link", "unlink", "archive", "merge")
SUGGESTION_TARGET_TYPES = (
    "research_direction",
    "member_direction_link",
    "project_direction_link",
    "resource_direction_link",
    "research_object_direction_link",
    "research_direction_relation",
)
```

Authoritative relations use real foreign keys. `KnowledgeSuggestion` and `KnowledgeChangeEvent` may use `target_type` plus `target_id` because they are workflow/audit records rather than the authoritative graph.

## Execution Prerequisites

Run this plan from an isolated worktree. Confirm that only intended files are present, then create the project-local backend environment if the worktree does not already contain it:

```bash
git status --short
python3.12 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
OPENCOLAB_ENV=test OPENCOLAB_DATABASE_URL=sqlite+aiosqlite:///:memory: \
  backend/.venv/bin/python -m pytest -q
```

Expected: the worktree is clean before implementation and the baseline suite reports `439 passed` with zero failures. If `backend/.venv` already exists, do not recreate it; run the dependency install and baseline test with that environment. Do not begin Task 1 until the baseline is green.

### Task 1: Add the foundation models and reversible migration

**Files:**

- Create: `backend/app/models/research_direction.py`
- Create: `backend/app/models/research_direction_link.py`
- Create: `backend/app/models/knowledge_governance.py`
- Create: `backend/alembic/versions/w4x5y6z7a8b9_add_lab_knowledge_foundation.py`
- Modify: `backend/app/models/__init__.py`
- Test: `tests/test_lab_knowledge_models.py`
- Test: `tests/test_lab_knowledge_foundation_migration.py`

- [ ] **Step 1: Write the failing metadata test**

```python
# tests/test_lab_knowledge_models.py
from sqlalchemy import CheckConstraint, UniqueConstraint

from app.core.database import Base
from app.models.knowledge_governance import (
    KnowledgeChangeEvent,
    KnowledgeSuggestion,
    ResearchDirectionSteward,
    ResearchGroupSteward,
)
from app.models.research_direction import ResearchDirection, ResearchDirectionRelation
from app.models.research_direction_link import (
    MemberResearchDirection,
    ProjectResearchDirection,
    ResearchAssetDirection,
    ResearchObjectDirection,
)


def test_lab_knowledge_tables_are_registered() -> None:
    assert {
        "research_directions",
        "research_direction_relations",
        "member_research_directions",
        "project_research_directions",
        "research_asset_directions",
        "research_object_directions",
        "research_group_stewards",
        "research_direction_stewards",
        "knowledge_suggestions",
        "knowledge_change_events",
    } <= set(Base.metadata.tables)


def test_direction_relation_has_order_and_uniqueness_constraints() -> None:
    table = ResearchDirectionRelation.__table__
    assert any(isinstance(item, CheckConstraint) for item in table.constraints)
    assert any(isinstance(item, UniqueConstraint) for item in table.constraints)


def test_steward_tables_use_foreign_keys_instead_of_polymorphic_scope_ids() -> None:
    assert "group_id" in ResearchGroupSteward.__table__.c
    assert "direction_id" in ResearchDirectionSteward.__table__.c
    assert KnowledgeSuggestion.__table__.c.target_id.nullable
    assert not KnowledgeChangeEvent.__table__.c.entity_id.nullable
```

- [ ] **Step 2: Run the metadata test and verify the imports fail**

Run:

```bash
OPENCOLAB_ENV=test OPENCOLAB_DATABASE_URL=sqlite+aiosqlite:///:memory: \
  backend/.venv/bin/python -m pytest tests/test_lab_knowledge_models.py -q
```

Expected: collection fails with `ModuleNotFoundError` for `app.models.research_direction`.

- [ ] **Step 3: Implement `ResearchDirection` and its symmetric relation**

```python
# backend/app/models/research_direction.py
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class ResearchDirection(Base):
    __tablename__ = "research_directions"
    __table_args__ = (
        UniqueConstraint("normalized_name", name="uq_research_directions_normalized_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255))
    normalized_name: Mapped[str] = mapped_column(String(255), index=True)
    summary: Mapped[str | None] = mapped_column(Text)
    background: Mapped[str | None] = mapped_column(Text)
    scope: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active", index=True)
    owner_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True)
    merged_into_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("research_directions.id", ondelete="RESTRICT"), index=True)
    last_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    review_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ResearchDirectionRelation(Base):
    __tablename__ = "research_direction_relations"
    __table_args__ = (
        CheckConstraint("direction_a_id < direction_b_id", name="ck_direction_relation_order"),
        CheckConstraint("relation_type = 'related'", name="ck_direction_relation_type"),
        UniqueConstraint("direction_a_id", "direction_b_id", name="uq_direction_relation_pair"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    direction_a_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_directions.id", ondelete="CASCADE"), index=True)
    direction_b_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_directions.id", ondelete="CASCADE"), index=True)
    relation_type: Mapped[str] = mapped_column(String(32), default="related", server_default="related")
    reason: Mapped[str] = mapped_column(Text)
    evidence_json: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 4: Implement the four explicit direction-link models**

```python
# backend/app/models/research_direction_link.py
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class MemberResearchDirection(Base):
    __tablename__ = "member_research_directions"
    __table_args__ = (UniqueConstraint("user_id", "direction_id", "valid_from", name="uq_member_direction_period"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    direction_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_directions.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(32), default="contributor", server_default="contributor")
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    source_type: Mapped[str] = mapped_column(String(32), default="human", server_default="human")
    source_id: Mapped[str | None] = mapped_column(String(36), index=True)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProjectResearchDirection(Base):
    __tablename__ = "project_research_directions"
    __table_args__ = (UniqueConstraint("project_id", "direction_id", name="uq_project_direction"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    direction_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_directions.id", ondelete="CASCADE"), index=True)
    reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ResearchAssetDirection(Base):
    __tablename__ = "research_asset_directions"
    __table_args__ = (UniqueConstraint("research_asset_id", "direction_id", name="uq_asset_direction"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    research_asset_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_assets.id", ondelete="CASCADE"), index=True)
    direction_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_directions.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ResearchObjectDirection(Base):
    __tablename__ = "research_object_directions"
    __table_args__ = (UniqueConstraint("research_object_id", "direction_id", "relation_type", name="uq_object_direction"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    research_object_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_objects.id", ondelete="CASCADE"), index=True)
    direction_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_directions.id", ondelete="CASCADE"), index=True)
    relation_type: Mapped[str] = mapped_column(String(32), default="belongs_to", server_default="belongs_to")
    reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 5: Implement the governance workflow models**

```python
# backend/app/models/knowledge_governance.py
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class ResearchGroupSteward(Base):
    __tablename__ = "research_group_stewards"
    __table_args__ = (UniqueConstraint("group_id", "user_id", name="uq_group_steward"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    group_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_groups.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class ResearchDirectionSteward(Base):
    __tablename__ = "research_direction_stewards"
    __table_args__ = (UniqueConstraint("direction_id", "user_id", name="uq_direction_steward"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    direction_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_directions.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class KnowledgeSuggestion(Base):
    __tablename__ = "knowledge_suggestions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    target_type: Mapped[str] = mapped_column(String(64), index=True)
    target_id: Mapped[str | None] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(32), index=True)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    evidence_json: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending", index=True)
    submitted_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True)
    submitted_by_type: Mapped[str] = mapped_column(String(20), default="human", server_default="human")
    reviewer_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True)
    decision_reason: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class KnowledgeChangeEvent(Base):
    __tablename__ = "knowledge_change_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(32), index=True)
    actor_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True)
    suggestion_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("knowledge_suggestions.id", ondelete="SET NULL"), index=True)
    before_json: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    after_json: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 6: Register all models and verify metadata tests pass**

Add explicit imports to `backend/app/models/__init__.py`, then run:

```bash
OPENCOLAB_ENV=test OPENCOLAB_DATABASE_URL=sqlite+aiosqlite:///:memory: \
  backend/.venv/bin/python -m pytest tests/test_lab_knowledge_models.py -q
```

Expected: `3 passed`.

- [ ] **Step 7: Create the Alembic migration from the current single head**

Create `backend/alembic/versions/w4x5y6z7a8b9_add_lab_knowledge_foundation.py` with:

```python
revision = "w4x5y6z7a8b9"
down_revision = "v3w4x5y6z7a8"
branch_labels = None
depends_on = None
```

Its `upgrade()` must create exactly the ten tables asserted in Step 1, all foreign-key indexes, the direction name and relation constraints, and no data backfill. Its `downgrade()` must drop tables in this order:

```text
knowledge_change_events
knowledge_suggestions
research_direction_stewards
research_group_stewards
research_object_directions
research_asset_directions
project_research_directions
member_research_directions
research_direction_relations
research_directions
```

- [ ] **Step 8: Write and run the migration round-trip test**

The test must create the minimum legacy tables referenced by foreign keys, insert one user, group, project, asset, and ResearchObject, run `upgrade()`, insert one row into every new table, run `downgrade()`, and assert that all legacy rows remain.

Run:

```bash
OPENCOLAB_ENV=test OPENCOLAB_DATABASE_URL=sqlite+aiosqlite:///:memory: \
  backend/.venv/bin/python -m pytest tests/test_lab_knowledge_foundation_migration.py -q
```

Expected: all migration tests pass and Alembic reports one head:

```bash
cd backend
OPENCOLAB_ENV=test OPENCOLAB_DATABASE_URL=sqlite+aiosqlite:///:memory: \
  .venv/bin/python -m alembic heads
```

Expected output contains only `w4x5y6z7a8b9 (head)`.

- [ ] **Step 9: Commit the foundation schema**

```bash
git add backend/app/models/__init__.py \
  backend/app/models/research_direction.py \
  backend/app/models/research_direction_link.py \
  backend/app/models/knowledge_governance.py \
  backend/alembic/versions/w4x5y6z7a8b9_add_lab_knowledge_foundation.py \
  tests/test_lab_knowledge_models.py \
  tests/test_lab_knowledge_foundation_migration.py
git commit -m "feat: add lab knowledge foundation schema"
```

### Task 2: Implement Research Direction lifecycle APIs

**Files:**

- Create: `backend/app/schemas/research_direction.py`
- Create: `backend/app/services/research_direction_service.py`
- Create: `backend/app/api/research_directions.py`
- Modify: `backend/app/main.py`
- Test: `tests/test_research_directions.py`

- [ ] **Step 1: Write failing API tests for authority and lifecycle**

```python
# tests/test_research_directions.py
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _create_direction(client: AsyncClient, headers: dict, name: str) -> dict:
    response = await client.post(
        "/api/v1/research-directions",
        json={"name": name},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


async def test_admin_can_create_and_archive_direction(client: AsyncClient, auth_headers: dict) -> None:
    created = await client.post(
        "/api/v1/research-directions",
        json={
            "name": "Single-cell analysis",
            "summary": "Methods for single-cell measurements",
            "background": "Lab-wide long-term context",
            "scope": "Single-cell assay and analysis methods",
        },
        headers=auth_headers,
    )
    assert created.status_code == 201
    direction_id = created.json()["id"]

    archived = await client.post(
        f"/api/v1/research-directions/{direction_id}/archive",
        headers=auth_headers,
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"


async def test_researcher_cannot_create_formal_direction(client: AsyncClient, researcher_headers: dict) -> None:
    response = await client.post(
        "/api/v1/research-directions",
        json={"name": "Unauthorized direction"},
        headers=researcher_headers,
    )
    assert response.status_code == 403


async def test_duplicate_normalized_name_returns_conflict(client: AsyncClient, auth_headers: dict) -> None:
    first = await client.post(
        "/api/v1/research-directions",
        json={"name": "Protein Design"},
        headers=auth_headers,
    )
    second = await client.post(
        "/api/v1/research-directions",
        json={"name": "  protein   design  "},
        headers=auth_headers,
    )
    assert first.status_code == 201
    assert second.status_code == 409


async def test_direction_list_uses_stable_keyset_cursor(client: AsyncClient, auth_headers: dict) -> None:
    for name in ("Direction C", "Direction A", "Direction B"):
        response = await client.post(
            "/api/v1/research-directions",
            json={"name": name},
            headers=auth_headers,
        )
        assert response.status_code == 201

    first_page = await client.get("/api/v1/research-directions?limit=2", headers=auth_headers)
    assert [item["name"] for item in first_page.json()["items"]] == ["Direction A", "Direction B"]
    cursor = first_page.json()["next_cursor"]
    second_page = await client.get(
        f"/api/v1/research-directions?limit=2&cursor={cursor}",
        headers=auth_headers,
    )
    assert [item["name"] for item in second_page.json()["items"]] == ["Direction C"]
```

- [ ] **Step 2: Run the direction tests and verify 404/405 failures**

```bash
OPENCOLAB_ENV=test OPENCOLAB_DATABASE_URL=sqlite+aiosqlite:///:memory: \
  backend/.venv/bin/python -m pytest tests/test_research_directions.py -q
```

Expected: endpoint tests fail because `/api/v1/research-directions` is not registered.

- [ ] **Step 3: Define exact Pydantic contracts**

```python
# backend/app/schemas/research_direction.py
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

DirectionStatus = Literal["active", "archived", "merged"]


class ResearchDirectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    summary: str | None = None
    background: str | None = None
    scope: str | None = None
    owner_id: str | None = None


class ResearchDirectionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    summary: str | None = None
    background: str | None = None
    scope: str | None = None
    owner_id: str | None = None
    last_confirmed_at: datetime | None = None
    review_due_at: datetime | None = None


class ResearchDirectionMerge(BaseModel):
    target_direction_id: str
    reason: str = Field(min_length=1, max_length=2000)


class ResearchDirectionResponse(BaseModel):
    id: str
    name: str
    summary: str | None
    background: str | None
    scope: str | None
    status: DirectionStatus
    owner_id: str | None
    merged_into_id: str | None
    last_confirmed_at: datetime | None
    review_due_at: datetime | None
    created_by: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ResearchDirectionPage(BaseModel):
    items: list[ResearchDirectionResponse]
    next_cursor: str | None = None


class DirectionRelationCreate(BaseModel):
    target_direction_id: str
    reason: str = Field(min_length=1, max_length=2000)
    evidence_json: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_nonempty_reason(self) -> "DirectionRelationCreate":
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValueError("Relation reason is required")
        return self
```

- [ ] **Step 4: Implement lifecycle service behavior**

`backend/app/services/research_direction_service.py` must expose these exact async interfaces:

- `create_direction(db: AsyncSession, *, actor: User, body: ResearchDirectionCreate) -> ResearchDirection`
- `get_direction(db: AsyncSession, *, direction_id: str) -> ResearchDirection`
- `list_directions(db: AsyncSession, *, query: str, status: str, limit: int, cursor: str | None) -> tuple[list[ResearchDirection], str | None]`
- `update_direction(db: AsyncSession, *, actor: User, direction_id: str, body: ResearchDirectionUpdate) -> ResearchDirection`
- `archive_direction(db: AsyncSession, *, actor: User, direction_id: str) -> ResearchDirection`
- `merge_direction(db: AsyncSession, *, actor: User, direction_id: str, body: ResearchDirectionMerge) -> ResearchDirection`

The required behavior is:

- Normalize names with `" ".join(name.split()).casefold()`.
- Admin and PI can create, merge, or archive in Phase 0.
- Admin and PI may update; PI authority is expanded to scoped governance in Task 4.
- Reject duplicate normalized active names with a conflict error.
- Reject merging a direction into itself, into a non-active target, or when either direction is already merged.
- Merge by setting `status="merged"` and `merged_into_id`; do not delete or rewrite links in Phase 0.
- Encode list cursors as URL-safe base64 JSON containing `normalized_name` and `id`; reject malformed cursors with a validation error.
- Fetch `limit + 1`, sort by `(normalized_name, id)`, and return at most `limit` rows.

- [ ] **Step 5: Add router endpoints and error mapping**

`backend/app/api/research_directions.py` must register:

```text
POST   /research-directions
GET    /research-directions
GET    /research-directions/{direction_id}
PATCH  /research-directions/{direction_id}
POST   /research-directions/{direction_id}/archive
POST   /research-directions/{direction_id}/merge
```

Map not-found to 404, permission failure to 403, conflict to 409, and malformed cursor/business validation to 422. Register the router in `backend/app/main.py` under `/api/v1`.

- [ ] **Step 6: Run focused tests and the existing group/project tests**

```bash
OPENCOLAB_ENV=test OPENCOLAB_DATABASE_URL=sqlite+aiosqlite:///:memory: \
  backend/.venv/bin/python -m pytest \
  tests/test_research_directions.py \
  tests/test_research_groups.py \
  tests/test_projects.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit the lifecycle API**

```bash
git add backend/app/schemas/research_direction.py \
  backend/app/services/research_direction_service.py \
  backend/app/api/research_directions.py \
  backend/app/main.py \
  tests/test_research_directions.py
git commit -m "feat: add research direction lifecycle"
```

### Task 3: Add explicit direction-to-direction relation APIs

**Files:**

- Modify: `backend/app/schemas/research_direction.py`
- Modify: `backend/app/services/research_direction_service.py`
- Modify: `backend/app/api/research_directions.py`
- Test: `tests/test_research_directions.py`

- [ ] **Step 1: Write a failing test for symmetric direction relations**

```python
async def test_related_direction_pair_is_canonical_and_requires_reason(client, auth_headers) -> None:
    first = await _create_direction(client, auth_headers, "Direction A")
    second = await _create_direction(client, auth_headers, "Direction B")
    created = await client.post(
        f"/api/v1/research-directions/{second['id']}/relations",
        json={"target_direction_id": first["id"], "reason": "Shared assay methods"},
        headers=auth_headers,
    )
    duplicate = await client.post(
        f"/api/v1/research-directions/{first['id']}/relations",
        json={"target_direction_id": second["id"], "reason": "Same pair"},
        headers=auth_headers,
    )
    assert created.status_code == 201
    assert created.json()["direction_a_id"] < created.json()["direction_b_id"]
    assert duplicate.status_code == 409
```

- [ ] **Step 2: Run the relation test and verify endpoint failure**

```bash
OPENCOLAB_ENV=test OPENCOLAB_DATABASE_URL=sqlite+aiosqlite:///:memory: \
  backend/.venv/bin/python -m pytest tests/test_research_directions.py \
  -k "related_direction" -q
```

Expected: the test fails because the relation endpoint does not exist.

- [ ] **Step 3: Add the response contract**

```python
class DirectionRelationResponse(BaseModel):
    id: str
    direction_a_id: str
    direction_b_id: str
    relation_type: Literal["related"]
    reason: str
    evidence_json: dict
    created_by: str
    created_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Implement relation behavior**

Add these exact service interfaces:

- `create_direction_relation(db: AsyncSession, *, actor: User, source_direction_id: str, body: DirectionRelationCreate) -> ResearchDirectionRelation`
- `list_direction_relations(db: AsyncSession, *, direction_id: str, limit: int, before_id: str | None) -> list[ResearchDirectionRelation]`
- `delete_direction_relation(db: AsyncSession, *, actor: User, relation_id: str) -> None`

Canonicalize the two direction IDs with `sorted((source_id, target_id))`. Reject self-relations, archived/merged directions, duplicate pairs, and empty reasons.

- [ ] **Step 5: Register endpoints**

```text
POST   /research-directions/{direction_id}/relations
GET    /research-directions/{direction_id}/relations
DELETE /research-direction-relations/{relation_id}
```

Return 201 for a direct PI/Admin relation.

- [ ] **Step 6: Run focused tests**

```bash
OPENCOLAB_ENV=test OPENCOLAB_DATABASE_URL=sqlite+aiosqlite:///:memory: \
  backend/.venv/bin/python -m pytest tests/test_research_directions.py -q
```

Expected: all direction tests pass.

- [ ] **Step 7: Commit explicit direction relations**

```bash
git add backend/app/schemas/research_direction.py \
  backend/app/services/research_direction_service.py \
  backend/app/api/research_directions.py \
  tests/test_research_directions.py
git commit -m "feat: add research direction relations"
```

### Task 4: Add scoped Knowledge Steward authority

**Files:**

- Create: `backend/app/schemas/knowledge_governance.py`
- Create: `backend/app/services/knowledge_governance_service.py`
- Create: `backend/app/api/knowledge_governance.py`
- Modify: `backend/app/main.py`
- Test: `tests/test_knowledge_governance.py`

- [ ] **Step 1: Write failing steward authority tests**

```python
# tests/test_knowledge_governance.py
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_governance import (
    KnowledgeChangeEvent,
    KnowledgeSuggestion,
    ResearchDirectionSteward,
    ResearchGroupSteward,
)
from app.models.research_direction import ResearchDirection
from app.models.research_direction_link import ResearchObjectDirection
from app.models.research_group import ResearchGroup, ResearchGroupMember
from app.models.research_object import ResearchObject

pytestmark = pytest.mark.asyncio


async def _create_group(client: AsyncClient, headers: dict, name: str) -> dict:
    response = await client.post(
        "/api/v1/research-groups",
        json={"name": name, "description": f"{name} description"},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


async def _add_member(
    client: AsyncClient,
    headers: dict,
    group_id: str,
    user_id: str,
    role: str,
):
    return await client.post(
        f"/api/v1/research-groups/{group_id}/members",
        json={"user_id": user_id, "role": role},
        headers=headers,
    )


@pytest_asyncio.fixture
async def group_steward_assignment(
    db: AsyncSession,
    admin_user,
    researcher_user,
) -> ResearchGroupSteward:
    group = ResearchGroup(name="Fixture Group", created_by=admin_user.id)
    db.add(group)
    await db.flush()
    db.add(
        ResearchGroupMember(
            group_id=group.id,
            user_id=researcher_user.id,
            role="postdoc",
            created_by=admin_user.id,
        )
    )
    assignment = ResearchGroupSteward(
        group_id=group.id,
        user_id=researcher_user.id,
        created_by=admin_user.id,
    )
    db.add(assignment)
    await db.flush()
    return assignment


@pytest_asyncio.fixture
async def direction_steward_assignment(
    db: AsyncSession,
    admin_user,
    researcher_user,
) -> ResearchDirectionSteward:
    direction = ResearchDirection(
        name="Fixture Direction",
        normalized_name="fixture direction",
        status="active",
        created_by=admin_user.id,
    )
    db.add(direction)
    await db.flush()
    assignment = ResearchDirectionSteward(
        direction_id=direction.id,
        user_id=researcher_user.id,
        created_by=admin_user.id,
    )
    db.add(assignment)
    await db.flush()
    return assignment


async def test_group_pi_can_assign_active_member_as_group_steward(
    client: AsyncClient,
    auth_headers: dict,
    pi_headers: dict,
    pi_user,
    researcher_user,
) -> None:
    group = await _create_group(client, auth_headers, "Stewarded Group")
    assert (await _add_member(client, auth_headers, group["id"], pi_user.id, "pi")).status_code == 201
    assert (
        await _add_member(client, auth_headers, group["id"], researcher_user.id, "postdoc")
    ).status_code == 201

    assigned = await client.post(
        f"/api/v1/knowledge-governance/groups/{group['id']}/stewards",
        json={"user_id": researcher_user.id},
        headers=pi_headers,
    )
    assert assigned.status_code == 201
    assert assigned.json()["group_id"] == group["id"]
    assert assigned.json()["revoked_at"] is None


async def test_group_steward_cannot_assign_another_steward(
    client: AsyncClient,
    researcher_headers: dict,
    group_steward_assignment,
    pi_user,
) -> None:
    response = await client.post(
        f"/api/v1/knowledge-governance/groups/{group_steward_assignment.group_id}/stewards",
        json={"user_id": pi_user.id},
        headers=researcher_headers,
    )
    assert response.status_code == 403


async def test_direction_steward_can_update_but_not_archive_direction(
    client: AsyncClient,
    researcher_headers: dict,
    direction_steward_assignment,
) -> None:
    direction_id = direction_steward_assignment.direction_id
    updated = await client.patch(
        f"/api/v1/research-directions/{direction_id}",
        json={"summary": "Steward-maintained summary"},
        headers=researcher_headers,
    )
    archived = await client.post(
        f"/api/v1/research-directions/{direction_id}/archive",
        headers=researcher_headers,
    )
    assert updated.status_code == 200
    assert archived.status_code == 403
```

- [ ] **Step 2: Run steward tests and verify endpoint failures**

```bash
OPENCOLAB_ENV=test OPENCOLAB_DATABASE_URL=sqlite+aiosqlite:///:memory: \
  backend/.venv/bin/python -m pytest tests/test_knowledge_governance.py \
  -k "steward" -q
```

Expected: tests fail because the governance router and authority helpers do not exist.

- [ ] **Step 3: Add steward request and response schemas**

```python
# backend/app/schemas/knowledge_governance.py
from datetime import datetime

from pydantic import BaseModel


class StewardAssignmentCreate(BaseModel):
    user_id: str


class GroupStewardResponse(BaseModel):
    id: str
    group_id: str
    user_id: str
    created_by: str
    created_at: datetime
    revoked_at: datetime | None

    model_config = {"from_attributes": True}


class DirectionStewardResponse(BaseModel):
    id: str
    direction_id: str
    user_id: str
    created_by: str
    created_at: datetime
    revoked_at: datetime | None

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Implement authority helpers**

`backend/app/services/knowledge_governance_service.py` must provide:

- `is_group_steward(db, group_id, user_id)` — true only for a non-revoked assignment, active group, and active group membership.
- `is_direction_steward(db, direction_id, user_id)` — true only for a non-revoked assignment and active direction.
- `can_govern_direction(db, actor, direction_id)` — true for Admin, PI, or active direction steward.
- `can_govern_member_direction(db, actor, user_id, direction_id)` — true for Admin/PI, direction steward, or a group steward in one of the target member's active groups.
- `can_govern_asset_direction(db, actor, asset_id, direction_id)` — true for Admin/PI, direction steward, or steward of the asset's owning group.
- `assign_group_steward`, `revoke_group_steward`, `assign_direction_steward`, and `revoke_direction_steward` — only Admin or the applicable PI manager may call them; a group steward candidate must be an active member of that group.

Reuse a revoked assignment by clearing `revoked_at`; do not insert a duplicate row that violates the unique constraint.

- [ ] **Step 5: Add steward endpoints**

Register `backend/app/api/knowledge_governance.py` with:

```text
POST   /knowledge-governance/groups/{group_id}/stewards
GET    /knowledge-governance/groups/{group_id}/stewards
DELETE /knowledge-governance/groups/{group_id}/stewards/{user_id}
POST   /knowledge-governance/directions/{direction_id}/stewards
GET    /knowledge-governance/directions/{direction_id}/stewards
DELETE /knowledge-governance/directions/{direction_id}/stewards/{user_id}
```

Return 201 for a new/reactivated assignment and 204 for revocation. Register the router in `backend/app/main.py`.

- [ ] **Step 6: Route direction updates through scoped authority**

Modify `update_direction` and direction-relation mutation functions to call `can_govern_direction`. Keep create, archive, and merge restricted to PI/Admin; a Steward cannot perform those actions.

- [ ] **Step 7: Run governance, direction, and group tests**

```bash
OPENCOLAB_ENV=test OPENCOLAB_DATABASE_URL=sqlite+aiosqlite:///:memory: \
  backend/.venv/bin/python -m pytest \
  tests/test_knowledge_governance.py \
  tests/test_research_directions.py \
  tests/test_research_groups.py -q
```

Expected: all tests pass.

- [ ] **Step 8: Commit scoped stewardship**

```bash
git add backend/app/schemas/knowledge_governance.py \
  backend/app/services/knowledge_governance_service.py \
  backend/app/api/knowledge_governance.py \
  backend/app/services/research_direction_service.py \
  backend/app/main.py \
  tests/test_knowledge_governance.py \
  tests/test_research_directions.py
git commit -m "feat: add scoped knowledge stewardship"
```

### Task 5: Implement suggestion review and immutable audit events

**Files:**

- Modify: `backend/app/schemas/knowledge_governance.py`
- Modify: `backend/app/schemas/research_direction.py`
- Modify: `backend/app/services/knowledge_governance_service.py`
- Modify: `backend/app/api/knowledge_governance.py`
- Modify: `backend/app/api/research_directions.py`
- Modify: `backend/app/services/research_direction_service.py`
- Test: `tests/test_knowledge_governance.py`

- [ ] **Step 1: Write failing suggestion decision tests**

```python
@pytest_asyncio.fixture
async def graduation_pair(
    db: AsyncSession,
    admin_user,
    researcher_user,
) -> tuple[ResearchDirection, ResearchObject]:
    direction = ResearchDirection(
        name="Graduation Direction",
        normalized_name="graduation direction",
        status="active",
        created_by=admin_user.id,
    )
    research_object = ResearchObject(
        type="hypothesis",
        title="Graduating Hypothesis",
        content="A mature testable hypothesis",
        content_json={},
        created_by=researcher_user.id,
    )
    db.add_all([direction, research_object])
    await db.flush()
    return direction, research_object


@pytest_asyncio.fixture
async def pending_object_direction_suggestion(
    db: AsyncSession,
    admin_user,
    researcher_user,
) -> KnowledgeSuggestion:
    direction = ResearchDirection(
        name="Suggestion Direction",
        normalized_name="suggestion direction",
        status="active",
        created_by=admin_user.id,
    )
    research_object = ResearchObject(
        type="hypothesis",
        title="Suggestion Hypothesis",
        content="Evidence-backed hypothesis",
        content_json={},
        created_by=researcher_user.id,
    )
    db.add_all([direction, research_object])
    await db.flush()
    suggestion = KnowledgeSuggestion(
        target_type="research_object_direction_link",
        action="link",
        payload_json={
            "research_object_id": research_object.id,
            "direction_id": direction.id,
            "relation_type": "belongs_to",
            "reason": "Validated project output",
        },
        evidence_json={},
        status="pending",
        submitted_by=researcher_user.id,
        submitted_by_type="human",
    )
    db.add(suggestion)
    await db.flush()
    return suggestion


@pytest_asyncio.fixture
async def approved_suggestion(
    db: AsyncSession,
    admin_user,
) -> KnowledgeSuggestion:
    suggestion = KnowledgeSuggestion(
        target_type="research_direction_relation",
        action="link",
        payload_json={},
        evidence_json={},
        status="approved",
        submitted_by=admin_user.id,
        submitted_by_type="human",
        reviewer_id=admin_user.id,
        decision_reason="Already decided",
    )
    db.add(suggestion)
    await db.flush()
    return suggestion


async def test_research_object_owner_can_submit_graduation_suggestion(
    client,
    researcher_headers,
    graduation_pair,
) -> None:
    direction, research_object = graduation_pair
    response = await client.post(
        f"/api/v1/research-directions/{direction.id}/research-objects",
        json={
            "research_object_id": research_object.id,
            "relation_type": "belongs_to",
            "reason": "The hypothesis matured into this direction",
        },
        headers=researcher_headers,
    )
    assert response.status_code == 202
    assert response.json()["status"] == "pending"
    assert response.json()["target_type"] == "research_object_direction_link"


async def test_approving_object_direction_suggestion_creates_link_and_audit_event(
    client,
    auth_headers,
    db,
    pending_object_direction_suggestion,
) -> None:
    response = await client.post(
        f"/api/v1/knowledge-governance/suggestions/{pending_object_direction_suggestion.id}/approve",
        json={"reason": "Validated by the direction owner"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "approved"

    link = await db.scalar(
        select(ResearchObjectDirection).where(
            ResearchObjectDirection.research_object_id
            == pending_object_direction_suggestion.payload_json["research_object_id"],
            ResearchObjectDirection.direction_id
            == pending_object_direction_suggestion.payload_json["direction_id"],
        )
    )
    event = await db.scalar(
        select(KnowledgeChangeEvent).where(
            KnowledgeChangeEvent.suggestion_id == pending_object_direction_suggestion.id
        )
    )
    assert link is not None
    assert event is not None
    assert event.after_json["direction_id"] == link.direction_id


async def test_rejected_suggestion_never_changes_authoritative_state(
    client,
    auth_headers,
    db,
    pending_object_direction_suggestion,
) -> None:
    response = await client.post(
        f"/api/v1/knowledge-governance/suggestions/{pending_object_direction_suggestion.id}/reject",
        json={"reason": "Insufficient evidence"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert await db.scalar(select(func.count()).select_from(ResearchObjectDirection)) == 0


async def test_decided_suggestion_cannot_be_decided_again(
    client,
    auth_headers,
    approved_suggestion,
) -> None:
    response = await client.post(
        f"/api/v1/knowledge-governance/suggestions/{approved_suggestion.id}/reject",
        json={"reason": "Second decision"},
        headers=auth_headers,
    )
    assert response.status_code == 409
```

- [ ] **Step 2: Run the decision tests and verify failures**

```bash
OPENCOLAB_ENV=test OPENCOLAB_DATABASE_URL=sqlite+aiosqlite:///:memory: \
  backend/.venv/bin/python -m pytest tests/test_knowledge_governance.py \
  -k "suggestion" -q
```

Expected: approval/rejection endpoints fail because they do not exist.

- [ ] **Step 3: Add exact suggestion schemas**

```python
from typing import Literal

from pydantic import BaseModel, Field

SuggestionStatus = Literal["pending", "approved", "rejected"]


class KnowledgeSuggestionCreate(BaseModel):
    target_type: Literal[
        "research_direction",
        "member_direction_link",
        "project_direction_link",
        "resource_direction_link",
        "research_object_direction_link",
        "research_direction_relation",
    ]
    target_id: str | None = None
    action: Literal["create", "update", "link", "unlink", "archive", "merge"]
    payload_json: dict = Field(default_factory=dict)
    evidence_json: dict = Field(default_factory=dict)


class SuggestionDecision(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class KnowledgeSuggestionResponse(BaseModel):
    id: str
    target_type: str
    target_id: str | None
    action: str
    payload_json: dict
    evidence_json: dict
    status: SuggestionStatus
    submitted_by: str | None
    submitted_by_type: str
    reviewer_id: str | None
    decision_reason: str | None
    decided_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
```

Add the graduation request to `backend/app/schemas/research_direction.py`:

```python
class ResearchObjectDirectionRequest(BaseModel):
    research_object_id: str
    relation_type: Literal["belongs_to", "informs"] = "belongs_to"
    reason: str = Field(min_length=1, max_length=2000)
```

- [ ] **Step 4: Implement suggestion submission and decision transactions**

Implement one transaction per decision:

1. Load the suggestion with a row lock when PostgreSQL is used.
2. Reject any status other than `pending`.
3. Re-evaluate the reviewer's current authority; never trust authority captured at submission time.
4. For `research_object_direction_link`, validate exact payload keys `research_object_id`, `direction_id`, `relation_type`, and `reason`, then insert `ResearchObjectDirection`.
5. For `research_direction_relation`, validate exact payload keys `source_direction_id`, `target_direction_id`, `reason`, and `evidence_json`, then insert a canonical `ResearchDirectionRelation`.
6. Keep other target types submit/list/reject-capable in Phase 0; approval returns 422 `Unsupported suggestion approval target` until the later phase owning that authoritative entity adds a handler.
7. Set reviewer, reason, status, and `decided_at`.
8. Insert one `KnowledgeChangeEvent` in the same transaction for approved suggestions; rejected suggestions retain their decision on the suggestion record and do not create an authoritative change event.

Do not add timers or default-accept logic.
Reject payload fields that could contain raw restricted content. Suggestion and audit JSON may contain identifiers, changed metadata fields, reasons, and safe evidence references only.

Add `submit_research_object_direction_suggestion`. It must verify that the requester owns the ResearchObject, that the direction is active, and that no identical authoritative link or pending suggestion exists. Register:

```text
POST /research-directions/{direction_id}/research-objects
```

Return 202 with `KnowledgeSuggestionResponse`; only the approval transaction creates `ResearchObjectDirection`.

- [ ] **Step 5: Add suggestion endpoints and pagination**

```text
POST /knowledge-governance/suggestions
GET  /knowledge-governance/suggestions?status=pending&limit=20&before_id={id}
GET  /knowledge-governance/suggestions/{suggestion_id}
POST /knowledge-governance/suggestions/{suggestion_id}/approve
POST /knowledge-governance/suggestions/{suggestion_id}/reject
```

The list endpoint returns only suggestions the requester can review, except that submitters may see their own suggestions. Sort by `(created_at DESC, id DESC)` and use `before_id` keyset pagination.

- [ ] **Step 6: Run governance tests**

```bash
OPENCOLAB_ENV=test OPENCOLAB_DATABASE_URL=sqlite+aiosqlite:///:memory: \
  backend/.venv/bin/python -m pytest tests/test_knowledge_governance.py -q
```

Expected: all governance tests pass.

- [ ] **Step 7: Commit suggestion governance**

```bash
git add backend/app/schemas/knowledge_governance.py \
  backend/app/schemas/research_direction.py \
  backend/app/services/knowledge_governance_service.py \
  backend/app/api/knowledge_governance.py \
  backend/app/api/research_directions.py \
  backend/app/services/research_direction_service.py \
  tests/test_knowledge_governance.py
git commit -m "feat: add knowledge suggestion review"
```

### Task 6: Establish the request-time authorization and revocation contract

**Files:**

- Create: `backend/app/services/knowledge_access_service.py`
- Modify: `backend/app/services/rag_service.py`
- Create: `tests/test_knowledge_access_service.py`
- Modify: `tests/test_rag_service.py`
- Create: `docs/lab-knowledge-os-v1-security-contract.md`

- [ ] **Step 1: Write failing current-permission tests**

```python
# tests/test_knowledge_access_service.py
import pytest
import pytest_asyncio

from app.core.governance import Capability
from app.models.research_asset import ResearchAsset
from app.services.access_policy_service import PolicyDecision
from app.services.knowledge_access_service import filter_authorized_asset_ids

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def candidate_assets(db, admin_user) -> tuple[ResearchAsset, ResearchAsset]:
    visible = ResearchAsset(
        asset_type="paper",
        title="Visible candidate",
        owner_id=admin_user.id,
        visibility_scope="lab_public",
        classification="public",
        catalog_status="published",
        lifecycle_status="active",
    )
    hidden = ResearchAsset(
        asset_type="paper",
        title="Hidden candidate",
        owner_id=admin_user.id,
        visibility_scope="lab_private",
        classification="confidential",
        catalog_status="published",
        lifecycle_status="active",
    )
    db.add_all([visible, hidden])
    await db.flush()
    return visible, hidden


async def test_filter_authorized_asset_ids_rechecks_each_asset(
    db,
    researcher_user,
    candidate_assets,
    monkeypatch,
) -> None:
    visible, hidden = candidate_assets

    async def fake_authorize_asset(*, asset, capability, **kwargs):
        return PolicyDecision(
            allowed=asset.id == visible.id,
            capability=capability,
            reason_code="test_policy",
        )

    monkeypatch.setattr(
        "app.services.knowledge_access_service.authorize_asset",
        fake_authorize_asset,
    )
    result = await filter_authorized_asset_ids(
        db,
        user=researcher_user,
        asset_ids=[visible.id, hidden.id],
        capability=Capability.METADATA_VIEW,
        project_id=None,
        purpose="Knowledge entity discovery",
    )
    assert result == [visible.id]


async def test_revoked_grant_stops_authorizing_without_reindex(
    db,
    researcher_user,
    candidate_assets,
    monkeypatch,
) -> None:
    _, hidden = candidate_assets
    policy_state = {"enabled": True}

    async def fake_authorize_asset(*, capability, **kwargs):
        return PolicyDecision(
            allowed=policy_state["enabled"],
            capability=capability,
            reason_code="test_policy",
        )

    monkeypatch.setattr(
        "app.services.knowledge_access_service.authorize_asset",
        fake_authorize_asset,
    )
    before = await filter_authorized_asset_ids(
        db,
        user=researcher_user,
        asset_ids=[hidden.id],
        capability=Capability.CONTENT_USE_IN_AGENT,
        project_id=None,
        purpose="Lab knowledge question",
    )
    policy_state["enabled"] = False
    after = await filter_authorized_asset_ids(
        db,
        user=researcher_user,
        asset_ids=[hidden.id],
        capability=Capability.CONTENT_USE_IN_AGENT,
        project_id=None,
        purpose="Lab knowledge question",
    )
    assert before == [hidden.id]
    assert after == []
```

- [ ] **Step 2: Run authorization tests and verify import failure**

```bash
OPENCOLAB_ENV=test OPENCOLAB_DATABASE_URL=sqlite+aiosqlite:///:memory: \
  backend/.venv/bin/python -m pytest tests/test_knowledge_access_service.py -q
```

Expected: collection fails because `knowledge_access_service` does not exist.

- [ ] **Step 3: Implement the shared authorization filter**

```python
# backend/app/services/knowledge_access_service.py
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.governance import Capability
from app.models.asset_revision import AssetRevision
from app.models.research_asset import ResearchAsset
from app.models.user import User
from app.services.access_policy_service import AccessContext, authorize_asset


async def filter_authorized_asset_ids(
    db: AsyncSession,
    *,
    user: User,
    asset_ids: list[str],
    capability: Capability,
    project_id: str | None,
    purpose: str,
) -> list[str]:
    if not asset_ids:
        return []
    assets = list(
        (
            await db.scalars(
                select(ResearchAsset).where(ResearchAsset.id.in_(asset_ids))
            )
        ).all()
    )
    assets_by_id = {asset.id: asset for asset in assets}
    allowed: list[str] = []
    for asset_id in asset_ids:
        asset = assets_by_id.get(asset_id)
        if asset is None:
            continue
        revision = (
            await db.get(AssetRevision, asset.current_revision_id)
            if asset.current_revision_id
            else None
        )
        decision = await authorize_asset(
            db,
            user=user,
            asset=asset,
            revision=revision,
            capability=capability,
            context=AccessContext(project_id=project_id, purpose=purpose),
        )
        if decision.allowed:
            allowed.append(asset_id)
    return allowed
```

- [ ] **Step 4: Route RAG candidate assets through the shared filter**

At the point where `backend/app/services/rag_service.py` converts Qdrant/source hits into governed assets, call `filter_authorized_asset_ids` with `CONTENT_USE_IN_AGENT`. Preserve Qdrant score order by filtering the original ordered ID list; do not sort the authorized result separately. Do not add an authorization-result cache in Phase 0.

- [ ] **Step 5: Add a RAG revocation regression test**

The test must return a private asset from the mocked vector store, authorize it once, disable the matching policy without modifying Qdrant, issue the same retrieval again, and assert that no chunk or snippet is returned the second time.

- [ ] **Step 6: Write the security contract**

`docs/lab-knowledge-os-v1-security-contract.md` must contain these sections:

```markdown
# Lab Knowledge OS v1 Security Contract
## Protected data and trust boundaries
## Request-time authorization sequence
## Qdrant is an untrusted candidate index
## Permission revocation and cache invalidation
## Derived records and safe summaries
## LLM egress rules
## Required automated abuse cases
## Phase 1 entry checklist
```

State explicitly that PostgreSQL policy is authoritative, Qdrant hits are candidates, permission-result caching is prohibited until a versioned invalidation design passes review, and raw query/answer text is excluded from local adoption events.

- [ ] **Step 7: Run focused security regressions**

```bash
OPENCOLAB_ENV=test OPENCOLAB_DATABASE_URL=sqlite+aiosqlite:///:memory: \
  backend/.venv/bin/python -m pytest \
  tests/test_knowledge_access_service.py \
  tests/test_rag_service.py \
  tests/test_research_assets.py -q
```

Expected: all tests pass.

- [ ] **Step 8: Commit the authorization contract**

```bash
git add backend/app/services/knowledge_access_service.py \
  backend/app/services/rag_service.py \
  tests/test_knowledge_access_service.py \
  tests/test_rag_service.py \
  docs/lab-knowledge-os-v1-security-contract.md
git commit -m "security: enforce request-time knowledge authorization"
```

### Task 7: Create and freeze the real-question benchmark gate

**Files:**

- Create: `docs/evaluations/lab-knowledge-os-v1-benchmark.schema.json`
- Create locally after the collection workshop: `evaluation-data/lab-knowledge-os-v1-benchmark.zh-CN.json`
- Create: `docs/evaluations/lab-knowledge-os-v1-benchmark-manifest.json`
- Create: `scripts/validate-lab-knowledge-benchmark.py`
- Modify: `.gitignore`
- Test: `tests/test_lab_knowledge_benchmark.py`

- [ ] **Step 1: Add the benchmark JSON schema**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Lab Knowledge OS v1 benchmark",
  "type": "object",
  "required": ["frozen_at", "questions"],
  "properties": {
    "frozen_at": {"type": "string", "format": "date"},
    "questions": {
      "type": "array",
      "minItems": 30,
      "maxItems": 30,
      "items": {
        "type": "object",
        "required": ["id", "category", "question", "expected_behavior", "permission_profiles", "rubric"],
        "properties": {
          "id": {"type": "string", "pattern": "^LK-[0-9]{3}$"},
          "category": {"enum": ["people", "research", "resources", "cross_entity"]},
          "question": {"type": "string", "minLength": 5},
          "expected_behavior": {"enum": ["answer", "no_answer", "permission_limited"]},
          "permission_profiles": {
            "type": "array",
            "minItems": 1,
            "items": {"enum": ["admin", "pi", "member_with_project_access", "member_without_project_access"]}
          },
          "rubric": {
            "type": "object",
            "required": ["required_entity_types", "required_source_titles", "notes"],
            "properties": {
              "required_entity_types": {"type": "array", "items": {"enum": ["person", "research_direction", "resource"]}},
              "required_source_titles": {"type": "array", "items": {"type": "string"}},
              "notes": {"type": "string"}
            }
          }
        }
      }
    }
  }
}
```

- [ ] **Step 2: Write validator tests before the validator**

Tests must assert rejection of 29 questions, wrong category distribution, duplicate IDs, fewer than six no-answer/permission-limited questions, fewer than six multi-permission questions, and acceptance of a compliant 30-question in-memory fixture.

- [ ] **Step 3: Implement the offline validator**

`scripts/validate-lab-knowledge-benchmark.py` must use only the Python standard library. It accepts one positional JSON path, validates required types/fields, unique IDs, exact count, exact category counts (8 people, 8 research, 8 resources, 6 cross-entity), at least six limited/no-answer cases, and at least six questions with two or more permission profiles. On success it prints only the SHA-256 digest and aggregate counts; it must never print question text, rubric text, source titles, or expected answers. It exits 0 on success, or prints validation errors that identify only field paths and exits 1.

- [ ] **Step 4: Run validator unit tests**

```bash
backend/.venv/bin/python -m pytest tests/test_lab_knowledge_benchmark.py -q
```

Expected: all validator tests pass.

- [ ] **Step 5: Run the human collection workshop**

Before entering any research content, add `evaluation-data/` to `.gitignore` and verify the target is ignored with `git check-ignore evaluation-data/lab-knowledge-os-v1-benchmark.zh-CN.json`. The product owner then facilitates a session with the PI and at least three real lab members. Enter questions verbatim; do not have an engineer or LLM rewrite them. Assign IDs `LK-001` through `LK-030`, complete the rubric with the evaluators, and save the approved file as `evaluation-data/lab-knowledge-os-v1-benchmark.zh-CN.json`.

- [ ] **Step 6: Freeze and validate the real dataset**

```bash
backend/.venv/bin/python scripts/validate-lab-knowledge-benchmark.py \
  evaluation-data/lab-knowledge-os-v1-benchmark.zh-CN.json
```

Expected: one success line containing the SHA-256 digest and aggregate counts, with no benchmark content.

Create `docs/evaluations/lab-knowledge-os-v1-benchmark-manifest.json` from that output. It may contain only `frozen_at`, `sha256`, category counts, limited/no-answer count, multi-permission count, and approval roles. It must not contain question text, rubric text, source titles, member names, record IDs, or signatures.

- [ ] **Step 7: Commit the benchmark gate after human approval**

```bash
git check-ignore evaluation-data/lab-knowledge-os-v1-benchmark.zh-CN.json
git add .gitignore \
  docs/evaluations/lab-knowledge-os-v1-benchmark.schema.json \
  docs/evaluations/lab-knowledge-os-v1-benchmark-manifest.json \
  scripts/validate-lab-knowledge-benchmark.py \
  tests/test_lab_knowledge_benchmark.py
git commit -m "test: add lab knowledge benchmark gate"
```

### Task 8: Perform migration inventory, dry run, and reconciliation

**Files:**

- Create: `docs/lab-knowledge-os-v1-migration-runbook.md`
- Modify only if a migration defect is found: `backend/alembic/versions/w4x5y6z7a8b9_add_lab_knowledge_foundation.py`
- Test only if a migration defect is found: `tests/test_lab_knowledge_foundation_migration.py`

- [ ] **Step 1: Write the migration runbook before running against copied data**

The runbook must include:

```markdown
# Lab Knowledge OS v1 Migration Runbook
## Scope and non-goals
## Required backup and restore proof
## Pre-migration inventory queries
## Duplicate and conflict report
## Upgrade command
## Post-migration reconciliation queries
## Downgrade command
## Rollback decision criteria
## Sign-off record
```

The pre/post queries must count users, active research-group memberships, projects, ResearchAssets by visibility, ResearchObjects by type, access policies, and all new tables. Since Phase 0 performs no automatic direction backfill, all new tables must be empty immediately after upgrade on copied production data.

- [ ] **Step 2: Create a disposable PostgreSQL database from a sanitized backup**

Use a database name dedicated to this run, record the backup identifier and checksum in the runbook sign-off, and do not use production. Provide connection details only through `OPENCOLAB_DATABASE_URL`; never commit them.

- [ ] **Step 3: Run the upgrade and reconciliation**

```bash
cd backend
OPENCOLAB_ENV=test .venv/bin/python -m alembic upgrade head
```

Run the documented reconciliation queries. Expected: all legacy counts remain equal and all new-table counts are zero.

- [ ] **Step 4: Run downgrade and restore proof**

```bash
cd backend
OPENCOLAB_ENV=test .venv/bin/python -m alembic downgrade v3w4x5y6z7a8
```

Expected: all new tables are removed, all legacy counts remain equal, and the application test suite can start against the downgraded copy.

- [ ] **Step 5: Fix migration defects with a red-green test**

If the dry run reveals a defect, first add the exact legacy shape/data to `tests/test_lab_knowledge_foundation_migration.py`, run it to reproduce the failure, make the smallest migration fix, and rerun the focused migration test. Do not edit previously deployed migrations after Phase 0 ships; create a follow-up migration instead.

- [ ] **Step 6: Commit the signed runbook**

```bash
git add docs/lab-knowledge-os-v1-migration-runbook.md
git commit -m "docs: add lab knowledge migration runbook"
```

### Task 9: Verify the Phase 0 exit gate

**Files:**

- Modify if necessary: files changed by Tasks 1–8
- Verify: `docs/superpowers/specs/2026-08-07-lab-knowledge-os-v1-prd.zh-CN.md`
- Verify: `docs/superpowers/plans/2026-08-09-lab-knowledge-os-v1-roadmap.md`

- [ ] **Step 1: Run focused Phase 0 tests**

```bash
OPENCOLAB_ENV=test OPENCOLAB_DATABASE_URL=sqlite+aiosqlite:///:memory: \
  backend/.venv/bin/python -m pytest \
  tests/test_lab_knowledge_models.py \
  tests/test_lab_knowledge_foundation_migration.py \
  tests/test_research_directions.py \
  tests/test_knowledge_governance.py \
  tests/test_knowledge_access_service.py \
  tests/test_lab_knowledge_benchmark.py \
  tests/test_rag_service.py -q
```

Expected: all focused tests pass.

- [ ] **Step 2: Run the complete backend suite**

```bash
OPENCOLAB_ENV=test OPENCOLAB_DATABASE_URL=sqlite+aiosqlite:///:memory: \
  backend/.venv/bin/python -m pytest -q
```

Expected: at least the baseline `439 passed`, plus all new Phase 0 tests, with zero failures.

- [ ] **Step 3: Run pre-commit and migration-head checks**

```bash
backend/.venv/bin/pre-commit run --all-files
cd backend
OPENCOLAB_ENV=test OPENCOLAB_DATABASE_URL=sqlite+aiosqlite:///:memory: \
  .venv/bin/python -m alembic heads
```

Expected: pre-commit exits 0 and Alembic reports only `w4x5y6z7a8b9 (head)`.

- [ ] **Step 4: Verify product/security manual gates**

Confirm all items:

- The gitignored local 30-question dataset is verbatim, validator-clean, and signed off by product owner plus PI.
- Its SHA-256 digest and aggregate counts match `docs/evaluations/lab-knowledge-os-v1-benchmark-manifest.json`.
- `git ls-files evaluation-data` returns no files, and Git contains no raw benchmark questions or rubrics.
- Security contract review is signed by backend owner and privacy/security reviewer.
- Sanitized PostgreSQL upgrade/downgrade and reconciliation are recorded.
- No People/Research/Resources end-user page or new Discovery Loop generation behavior was added.
- No secret, raw query text, answer text, or unauthorized content appears in logs or benchmark metadata.

- [ ] **Step 5: Record Phase 0 completion and create the Phase 1 planning task**

Update the implementation tracking issue with test counts, migration sign-off, security review, benchmark checksum, and links to all Phase 0 commits. Create a separate planning task for `docs/superpowers/plans/2026-08-09-lab-knowledge-os-v1-resources.md`; do not start Resource implementation from this Foundation plan.

- [ ] **Step 6: Commit any verification-only documentation**

```bash
git add docs/lab-knowledge-os-v1-security-contract.md \
  docs/lab-knowledge-os-v1-migration-runbook.md
git commit -m "docs: record lab knowledge foundation verification"
```

If the files are unchanged because prior tasks already committed the final sign-offs, skip this commit instead of creating an empty commit.
