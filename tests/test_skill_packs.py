import io
import json
import shutil
import zipfile

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message
from app.models.orchestration_run import OrchestrationRun
from app.models.project import Project
from app.models.research_asset import ProjectAssetLink, ResearchAsset
from app.models.session import Session
from app.models.skill_pack import SkillPackRecord
from app.models.source import Chunk, Source
from app.models.task_definition import TaskDefinitionRecord
from app.models.user import User, Workspace
from app.schemas.skill_pack import SkillPackResponse
from app.services.skill_pack_service import (
    SkillPackValidationError,
    build_skill_pack_prompt,
    get_current_skill_pack,
    prepare_skill_run_workspace,
    store_skill_pack_zip,
)

pytestmark = pytest.mark.asyncio

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


async def test_store_skill_pack_zip_rejects_disallowed_extension(
    db: AsyncSession, tmp_path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr("app.services.skill_pack_service.settings.skill_pack_dir", str(tmp_path))
    with pytest.raises(SkillPackValidationError, match="not allowed"):
        await store_skill_pack_zip(
            make_zip({"SKILL.md": SKILL_MD, "evil.exe": "MZ"}),
            db=db,
            created_by=None,
        )


async def test_store_skill_pack_zip_rejects_invalid_front_matter(
    db: AsyncSession, tmp_path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr("app.services.skill_pack_service.settings.skill_pack_dir", str(tmp_path))
    with pytest.raises(SkillPackValidationError, match="front matter"):
        await store_skill_pack_zip(
            make_zip({"SKILL.md": "# No front matter here"}),
            db=db,
            created_by=None,
        )


async def test_store_skill_pack_zip_rejects_non_utf8_skill_md(
    db: AsyncSession, tmp_path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr("app.services.skill_pack_service.settings.skill_pack_dir", str(tmp_path))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("SKILL.md", b"\xff\xfe---\nname: x\n---")
    with pytest.raises(SkillPackValidationError, match="UTF-8"):
        await store_skill_pack_zip(buffer.getvalue(), db=db, created_by=None)


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
    db.expire_all()
    kept = await db.scalar(
        select(TaskDefinitionRecord).where(TaskDefinitionRecord.id == "skill-pack-gap-hunter")
    )
    assert kept is not None and kept.is_enabled is False  # task row kept, disabled


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


async def _always_authorized(**kwargs) -> bool:
    return True


async def _seed_project_material(db: AsyncSession, user: User, include_chunks: bool = True):
    workspace = await db.scalar(select(Workspace).where(Workspace.researcher_id == user.id))
    project = Project(name="Pack project", description=None)
    source = Source(
        type="file", name="paper.pdf", content_hash="h1", content_path="x",
        processing_state="ready", owner_id=user.id,
    )
    db.add_all([project, source])
    await db.flush()
    if include_chunks:
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


@pytest.mark.parametrize("selection_mode", ["default", "empty", "selected"])
async def test_prepare_skill_run_workspace_exports_parsed_materials(
    db: AsyncSession, admin_user: User, tmp_path, monkeypatch: pytest.MonkeyPatch,
    selection_mode: str,
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
    other_source = Source(type="file", name="other.pdf", owner_id=admin_user.id)
    db.add(other_source)
    await db.flush()
    db.add(Chunk(source_id=other_source.id, chunk_index=0, text="Unselected material."))

    async def fake_collect_project_source_ids(**kwargs):
        return [source.id, other_source.id]

    monkeypatch.setattr(
        "app.services.skill_pack_service.collect_project_source_ids",
        fake_collect_project_source_ids,
    )
    selection = {"default": None, "empty": [], "selected": [source.id]}[selection_mode]

    sandbox_cwd = await prepare_skill_run_workspace(
        db=db, run_id="run-1", pack=pack, session=session, user=admin_user,
        source_ids=selection,
    )

    assert sandbox_cwd == "/workspace/skill-runs/run-1"
    run_dir = tmp_path / "workspace" / "skill-runs" / "run-1"
    assert (run_dir / "SKILL.md").exists()
    assert (run_dir / "scripts" / "helper.py").exists()
    manifest = json.loads((run_dir / "materials" / "manifest.json").read_text(encoding="utf-8"))
    if selection_mode == "empty":
        assert manifest["materials"] == []
        assert not list((run_dir / "materials").glob("*.md"))
        return
    material = (run_dir / "materials" / f"{source.id}.md").read_text(encoding="utf-8")
    assert "First part." in material and "Second part." in material
    expected_ids = {source.id, other_source.id} if selection_mode == "default" else {source.id}
    assert {entry["source_id"] for entry in manifest["materials"]} == expected_ids
    assert (run_dir / "materials" / f"{other_source.id}.md").exists() == (selection_mode == "default")
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


async def _never_authorized(**kwargs) -> bool:
    return False


def _patch_workspace_settings(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setattr(
        "app.services.skill_pack_service.settings.skill_pack_dir", str(tmp_path / "packs")
    )
    monkeypatch.setattr(
        "app.services.skill_pack_service.settings.codex_runtime_workspace_dir",
        str(tmp_path / "workspace"),
    )
    monkeypatch.setattr(
        "app.services.skill_pack_service.settings.codex_runtime_sandbox_workspace_dir",
        "/workspace",
    )


async def test_prepare_skill_run_workspace_skips_sources_without_parsed_text(
    db: AsyncSession, admin_user: User, tmp_path, monkeypatch: pytest.MonkeyPatch
):
    _patch_workspace_settings(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "app.services.research_context.can_user_use_source_in_agent",
        _always_authorized,
    )
    pack = await store_skill_pack_zip(
        make_zip({"SKILL.md": SKILL_MD}),
        db=db,
        created_by=admin_user.id,
    )
    project, source, session = await _seed_project_material(
        db, admin_user, include_chunks=False
    )

    sandbox_cwd = await prepare_skill_run_workspace(
        db=db, run_id="run-skip", pack=pack, session=session, user=admin_user
    )

    assert sandbox_cwd == "/workspace/skill-runs/run-skip"
    run_dir = tmp_path / "workspace" / "skill-runs" / "run-skip"
    manifest = json.loads((run_dir / "materials" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["materials"][0]["source_id"] == source.id
    assert manifest["materials"][0]["status"] == "skipped"
    assert manifest["materials"][0]["reason"] == "no parsed text"
    assert manifest["materials"][0]["title"] == "paper.pdf"
    assert not (run_dir / "materials" / f"{source.id}.md").exists()


async def test_prepare_skill_run_workspace_excludes_unauthorized_sources(
    db: AsyncSession, admin_user: User, tmp_path, monkeypatch: pytest.MonkeyPatch
):
    _patch_workspace_settings(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "app.services.research_context.can_user_use_source_in_agent",
        _never_authorized,
    )
    pack = await store_skill_pack_zip(
        make_zip({"SKILL.md": SKILL_MD}),
        db=db,
        created_by=admin_user.id,
    )
    project, source, session = await _seed_project_material(db, admin_user)

    sandbox_cwd = await prepare_skill_run_workspace(
        db=db, run_id="run-denied", pack=pack, session=session, user=admin_user
    )

    assert sandbox_cwd == "/workspace/skill-runs/run-denied"
    run_dir = tmp_path / "workspace" / "skill-runs" / "run-denied"
    manifest = json.loads((run_dir / "materials" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["materials"] == []
    assert not list((run_dir / "materials").glob("*.md"))


def test_build_skill_pack_prompt_without_memories():
    from app.services.research_context import ResearchExecutionContext

    context = ResearchExecutionContext()
    prompt = build_skill_pack_prompt(goal="Find the gaps", memories=context)
    assert "## Research Memory" not in prompt
    assert "## User Goal" in prompt
    assert "Find the gaps" in prompt


async def test_prepare_skill_run_workspace_clears_stale_files_on_rerun(
    db: AsyncSession, admin_user: User, tmp_path, monkeypatch: pytest.MonkeyPatch
):
    _patch_workspace_settings(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "app.services.research_context.can_user_use_source_in_agent",
        _always_authorized,
    )
    pack = await store_skill_pack_zip(
        make_zip({"SKILL.md": SKILL_MD}),
        db=db,
        created_by=admin_user.id,
    )
    project, source, session = await _seed_project_material(db, admin_user)

    await prepare_skill_run_workspace(
        db=db, run_id="run-rerun", pack=pack, session=session, user=admin_user
    )
    run_dir = tmp_path / "workspace" / "skill-runs" / "run-rerun"
    stale = run_dir / "materials" / "stale.md"
    stale.write_text("stale", encoding="utf-8")

    await prepare_skill_run_workspace(
        db=db, run_id="run-rerun", pack=pack, session=session, user=admin_user
    )

    assert not stale.exists()
    assert (run_dir / "materials" / f"{source.id}.md").exists()


async def test_prepare_skill_run_workspace_missing_pack_files_raises(
    db: AsyncSession, admin_user: User, tmp_path, monkeypatch: pytest.MonkeyPatch
):
    _patch_workspace_settings(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "app.services.research_context.can_user_use_source_in_agent",
        _always_authorized,
    )
    pack = await store_skill_pack_zip(
        make_zip({"SKILL.md": SKILL_MD}),
        db=db,
        created_by=admin_user.id,
    )
    shutil.rmtree(tmp_path / "packs" / pack.storage_path)
    project, source, session = await _seed_project_material(db, admin_user)

    with pytest.raises(FileNotFoundError):
        await prepare_skill_run_workspace(
            db=db, run_id="run-missing", pack=pack, session=session, user=admin_user
        )


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
    await db.commit()

    session_response = await client.post(
        "/api/v1/sessions",
        json={"title": "Q&A", "project_id": project.id, "task_id": "project-qa"},
        headers=auth_headers,
    )
    assert session_response.status_code == 201

    response = await client.post(
        f"/api/v1/sessions/{session_response.json()['id']}/orchestration-runs/skill-pack",
        json={"goal": "Run something"},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Task is not bound to a skill pack"


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

    run = await db.scalar(
        select(OrchestrationRun).where(OrchestrationRun.session_id == session_id)
    )
    assert run is not None
    assert run.status == "failed"
    assert run.error_code == "codex_runtime_failed"
    assert run.error_message == "sandbox down"


async def test_skill_pack_run_rejects_task_scoped_to_other_project(
    client: AsyncClient, auth_headers, db: AsyncSession, admin_user: User,
    tmp_path, monkeypatch: pytest.MonkeyPatch,
):
    session_id = await _start_pack_session(
        client, auth_headers, db, admin_user, tmp_path, monkeypatch
    )
    project_a_id = (await db.get(Session, session_id)).project_id

    db.add(
        TaskDefinitionRecord(
            id="scoped-pack-task",
            version=1,
            name="Scoped Pack Task",
            description="Pack task scoped to another project.",
            workflow_id="skill-pack",
            skill_pack_id="gap-hunter",
            input_schema={"type": "object"},
            starter_prompts=[],
            project_context_policy={},
            result_presentation={"type": "assistant_message", "runtime": "codex"},
            is_enabled=True,
            project_ids=[project_a_id],
        )
    )
    project_b = Project(name="Other project", description=None)
    db.add(project_b)
    await db.commit()

    session_b_response = await client.post(
        "/api/v1/sessions",
        json={"title": "Other", "project_id": project_b.id},
        headers=auth_headers,
    )
    assert session_b_response.status_code == 201

    response = await client.post(
        f"/api/v1/sessions/{session_b_response.json()['id']}/orchestration-runs/skill-pack",
        json={"goal": "Find the gaps", "task_id": "scoped-pack-task"},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Task not found"


async def test_skill_pack_run_progress_endpoint_returns_live_events(
    client: AsyncClient, auth_headers, db: AsyncSession, admin_user: User,
    tmp_path, monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "app.services.orchestration_service.settings.codex_runtime_workspace_dir",
        str(tmp_path / "workspace"),
    )
    _project, _source, session = await _seed_project_material(db, admin_user)
    run = OrchestrationRun(
        session_id=session.id,
        task_id="skill-pack-gap-hunter",
        turn_index=1,
        status="running",
        created_by=admin_user.id,
    )
    db.add(run)
    await db.commit()

    progress_dir = tmp_path / "workspace" / "skill-runs" / run.id
    progress_dir.mkdir(parents=True)
    (progress_dir / "progress.jsonl").write_text(
        '{"type": "turn.started"}\n'
        '{"type": "item.completed", "item": {"type": "reasoning", "text": "Reading SKILL.md"}}\n'
        "not-json-line\n",
        encoding="utf-8",
    )

    response = await client.get(
        f"/api/v1/sessions/{session.id}/orchestration-runs/progress",
        headers=auth_headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == run.id
    assert payload["status"] == "running"
    assert len(payload["events"]) == 3
    assert payload["events"][1]["item"]["text"] == "Reading SKILL.md"
    assert payload["events"][2] == {"type": "stdout", "text": "not-json-line"}
