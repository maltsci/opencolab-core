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
from app.models.research_asset import ProjectAssetLink  # noqa: F401  (used by collect query)
from app.models.session import Session
from app.models.skill_pack import SkillPackRecord
from app.models.source import Chunk, Source
from app.models.task_definition import TaskDefinitionRecord
from app.models.trace import SourceExtraction
from app.models.user import User
from app.services.research_context import (
    ResearchExecutionContext,
    collect_project_source_ids,
)
from app.services.source_group_service import expand_source_ids_for_rag

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
    starter_prompt = payload.get("starter_prompt")
    return {
        "id": pack_id,
        "name": str(payload["name"]).strip(),
        "description": str(payload["description"]).strip(),
        "starter_prompt": str(starter_prompt).strip() if starter_prompt else None,
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


async def _upsert_bound_task(
    db: AsyncSession,
    pack: SkillPackRecord,
    *,
    starter_prompt: str | None = None,
) -> None:
    starter_prompts = [
        starter_prompt or f"Use {pack.name} for the current project task."
    ]
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
                starter_prompts=starter_prompts,
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
    task.starter_prompts = starter_prompts


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
        try:
            skill_md = archive.read("SKILL.md").decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SkillPackValidationError("SKILL.md must be valid UTF-8") from exc
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
    await _upsert_bound_task(db, pack, starter_prompt=meta["starter_prompt"])
    await db.commit()
    await db.refresh(pack)
    return pack


def build_skill_pack_prompt(
    *,
    goal: str,
    memories: ResearchExecutionContext,
    project_instructions: str | None = None,
) -> str:
    parts = [
        "Read ./SKILL.md and follow it exactly to accomplish the user's goal below.",
        (
            "Project materials (parsed text) are in ./materials/ — "
            "see ./materials/manifest.json for the index."
        ),
        "Write your final answer as your last message.",
    ]
    if project_instructions and project_instructions.strip():
        parts.extend(["## Project Instructions", project_instructions.strip()])
    parts.extend([
        "",
        "## User Goal",
        goal,
    ])
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
    source_ids: list[str] | None = None,
) -> str | None:
    if not settings.codex_runtime_workspace_dir:
        return None

    run_dir = Path(settings.codex_runtime_workspace_dir) / "skill-runs" / run_id
    if run_dir.exists():
        shutil.rmtree(run_dir)
    materials_dir = run_dir / "materials"
    materials_dir.mkdir(parents=True, exist_ok=True)

    pack_root = Path(settings.skill_pack_dir) / pack.storage_path
    if not pack_root.is_dir():
        raise FileNotFoundError(
            f"Skill pack files missing on disk: {pack.storage_path}"
        )
    for item in pack_root.rglob("*"):
        if item.is_file():
            target = run_dir / item.relative_to(pack_root)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)

    project_source_ids = await collect_project_source_ids(
        db=db,
        project_id=session.project_id,
        user=user,
    )
    if source_ids is None:
        source_ids = project_source_ids
    else:
        requested_source_ids = await expand_source_ids_for_rag(source_ids, db)
        project_source_id_set = set(project_source_ids)
        source_ids = [
            source_id for source_id in requested_source_ids
            if source_id in project_source_id_set
        ]
        if requested_source_ids and not source_ids:
            raise ValueError("Selected sources are unavailable in this project")
    manifest_entries: list[dict] = []
    for source_id in source_ids:
        exported = await _export_source_material(db, source_id)
        if exported is None:
            source = await db.get(Source, source_id)
            manifest_entries.append(
                {
                    "source_id": source_id,
                    "title": source.name if source else source_id,
                    "status": "skipped",
                    "reason": "no parsed text",
                }
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
