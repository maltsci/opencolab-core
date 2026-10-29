from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.research_asset import ProjectAssetLink, ResearchAsset
from app.models.research_object import ResearchObject
from app.models.session import Session
from app.models.source import Chunk, Source
from app.models.user import User
from app.services.rag_service import _rag_chunks
from app.services.sharing_service import can_user_use_source_in_agent


EVIDENCE_QUERY_CUES = (
    "experimental model",
    "experimental models",
    "experiment model",
    "main result",
    "main results",
    "mechanism evidence",
    "实验模型",
    "实验结果",
    "主要结果",
    "机制证据",
)
MODEL_SECTION_CUES = (
    "cell culture",
    "cell line",
    "animal",
    "microorganism",
    "tissue microarray",
    "transfection",
)
RESULT_SECTION_PATTERN = re.compile(r"^#{2,4}\s*3\.\d", re.MULTILINE)
METHOD_SECTION_PATTERN = re.compile(r"^#{2,4}\s*2\.\d", re.MULTILINE)


@dataclass(slots=True)
class ResearchContextChunk:
    source_id: str
    source_name: str
    chunk_id: str
    text: str


@dataclass(slots=True)
class ResearchContextMemory:
    id: str
    type: str
    title: str | None
    content: str | None


@dataclass(slots=True)
class ResearchExecutionContext:
    chunks: list[ResearchContextChunk] = field(default_factory=list)
    memories: list[ResearchContextMemory] = field(default_factory=list)


async def collect_project_source_ids(
    *,
    db: AsyncSession,
    project_id: str | None,
    user: User,
) -> list[str]:
    if not project_id:
        return []
    result = await db.execute(
        select(ResearchAsset)
        .outerjoin(ProjectAssetLink, ProjectAssetLink.asset_id == ResearchAsset.id)
        .where(
            ResearchAsset.source_id.is_not(None),
            ResearchAsset.publication_status == "active",
            ProjectAssetLink.project_id == project_id,
        )
        .order_by(ResearchAsset.updated_at.desc(), ResearchAsset.id.desc())
    )
    source_ids: list[str] = []
    for asset in result.scalars().all():
        if asset.source_id in source_ids:
            continue
        if (
            asset.source_id
            and await can_user_use_source_in_agent(
                user=user,
                source_id=asset.source_id,
                project_id=project_id,
                purpose="Use source in project research context",
                agent_run_id=f"project-context:{project_id}",
                db=db,
            )
        ):
            source_ids.append(asset.source_id)
    return source_ids


def _truncate_text(value: str | None, limit: int) -> str:
    if not value:
        return ""
    text = value.strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def _requires_evidence_coverage(query: str) -> bool:
    normalized = query.lower()
    return any(cue in normalized for cue in EVIDENCE_QUERY_CUES)


def _dominant_retrieval_source(retrieved: list[dict]) -> str | None:
    if not retrieved:
        return None
    scores: dict[str, tuple[int, float]] = {}
    for item in retrieved:
        source_id = item["source_id"]
        count, best_score = scores.get(source_id, (0, 0.0))
        scores[source_id] = (count + 1, max(best_score, float(item.get("score", 0))))
    return max(scores, key=lambda source_id: scores[source_id])


def _select_evidence_coverage_chunks(
    chunks: list[Chunk],
    max_chunks: int,
) -> list[Chunk]:
    """Select methods and result sections for evidence-oriented questions."""
    method_chunks = [
        chunk
        for chunk in chunks
        if METHOD_SECTION_PATTERN.search(chunk.text)
        and any(cue in chunk.text.lower() for cue in MODEL_SECTION_CUES)
    ]
    result_chunks = [
        chunk for chunk in chunks if RESULT_SECTION_PATTERN.search(chunk.text)
    ]
    method_limit = max(1, max_chunks // 3)
    selected = method_chunks[:method_limit]
    selected_ids = {chunk.id for chunk in selected}
    for chunk in result_chunks:
        if chunk.id not in selected_ids:
            selected.append(chunk)
            selected_ids.add(chunk.id)
        if len(selected) >= max_chunks:
            break
    if len(selected) < max_chunks:
        for chunk in chunks:
            if chunk.id not in selected_ids:
                selected.append(chunk)
                selected_ids.add(chunk.id)
            if len(selected) >= max_chunks:
                break
    return selected


async def build_research_execution_context(
    *,
    session_id: str,
    user_id: str,
    source_ids: list[str],
    db: AsyncSession,
    query: str | None = None,
    max_chunks: int = 6,
    max_memories: int = 6,
    max_text_chars: int = 1200,
) -> ResearchExecutionContext:
    chunks: list[ResearchContextChunk] = []
    if source_ids:
        user = await db.get(User, user_id)
        session = await db.get(Session, session_id)
        authorized_source_ids = []
        if user is not None and session is not None:
            for source_id in source_ids:
                if await can_user_use_source_in_agent(
                    user=user,
                    source_id=source_id,
                    project_id=session.project_id,
                    purpose="Fetch source content for workflow execution",
                    agent_run_id=f"execution-context:{session_id}",
                    db=db,
                ):
                    authorized_source_ids.append(source_id)
        if query and authorized_source_ids:
            retrieved = await _rag_chunks(query, authorized_source_ids, db, max_chunks)
            if _requires_evidence_coverage(query):
                dominant_source_id = _dominant_retrieval_source(retrieved)
                if dominant_source_id:
                    document_chunks = await db.scalars(
                        select(Chunk)
                        .where(Chunk.source_id == dominant_source_id)
                        .order_by(Chunk.chunk_index)
                    )
                    coverage_chunks = _select_evidence_coverage_chunks(
                        list(document_chunks), max_chunks
                    )
                    if coverage_chunks:
                        retrieved = [
                            {
                                "chunk_id": chunk.id,
                                "source_id": chunk.source_id,
                                "text": chunk.text,
                            }
                            for chunk in coverage_chunks
                        ]
            source_names = dict((await db.execute(
                select(Source.id, Source.name).where(Source.id.in_(authorized_source_ids))
            )).all())
            chunks = [
                ResearchContextChunk(
                    source_id=item["source_id"],
                    source_name=source_names[item["source_id"]],
                    chunk_id=item["chunk_id"],
                    text=_truncate_text(item["text"], max_text_chars),
                )
                for item in retrieved
            ]
        else:
            chunk_rows = await db.execute(
                select(Chunk, Source.name)
                .join(Source, Source.id == Chunk.source_id)
                .where(Chunk.source_id.in_(authorized_source_ids))
                .order_by(Chunk.source_id, Chunk.chunk_index)
                .limit(max_chunks)
            )
            chunks = [
                ResearchContextChunk(
                    source_id=chunk.source_id,
                    source_name=source_name,
                    chunk_id=chunk.id,
                    text=_truncate_text(chunk.text, max_text_chars),
                )
                for chunk, source_name in chunk_rows.all()
            ]

    memory_rows = await db.execute(
        select(ResearchObject)
        .where(ResearchObject.created_by == user_id)
        .where(ResearchObject.content_json["session_id"].as_string() == session_id)
        .order_by(ResearchObject.created_at.desc(), ResearchObject.id.desc())
        .limit(max_memories)
    )
    memories = [
        ResearchContextMemory(
            id=item.id,
            type=item.type,
            title=item.title,
            content=_truncate_text(item.content, max_text_chars),
        )
        for item in memory_rows.scalars().all()
    ]

    return ResearchExecutionContext(chunks=chunks, memories=memories)


def format_research_context_markdown(
    *,
    task_input: dict[str, Any],
    context: ResearchExecutionContext,
) -> str:
    sections = [
        "# OpenColab Research Context",
        "## Task Input",
        "```json",
        json.dumps(task_input, ensure_ascii=False, indent=2),
        "```",
    ]

    if context.chunks:
        sections.append("## Project Source Excerpts")
        for chunk in context.chunks:
            sections.extend(
                [
                    f"### {chunk.source_name}",
                    f"- source_id: `{chunk.source_id}`",
                    f"- chunk_id: `{chunk.chunk_id}`",
                    "",
                    chunk.text,
                ]
            )

    if context.memories:
        sections.append("## Research Memory")
        for memory in context.memories:
            title = memory.title or memory.id
            sections.extend(
                [
                    f"### {memory.type}: {title}",
                    f"- object_id: `{memory.id}`",
                    "",
                    memory.content or "",
                ]
            )

    return "\n\n".join(section for section in sections if section != "")


def write_codex_context_workspace(
    *,
    workflow_run_id: str,
    task_input: dict[str, Any],
    context: ResearchExecutionContext,
) -> str | None:
    if not settings.codex_runtime_workspace_dir:
        return None

    host_root = Path(settings.codex_runtime_workspace_dir)
    run_dir = host_root / "workflow-runs" / workflow_run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "context.md").write_text(
        format_research_context_markdown(task_input=task_input, context=context),
        encoding="utf-8",
    )

    sandbox_root = settings.codex_runtime_sandbox_workspace_dir
    if not sandbox_root:
        return str(run_dir)
    return str(Path(sandbox_root) / "workflow-runs" / workflow_run_id)
