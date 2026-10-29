import json
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.message import Message
from app.models.orchestration_run import OrchestrationRun
from app.models.project import Project
from app.models.session import Session
from app.models.user import User, Workspace
from app.services.codex_runtime import run_codex_runtime
from app.services.research_context import (
    ResearchExecutionContext,
    build_research_execution_context,
    collect_project_source_ids,
    format_research_context_markdown,
)
from app.services.skill_pack_service import (
    build_skill_pack_prompt,
    get_current_skill_pack,
    prepare_skill_run_workspace,
)
from app.services.source_group_service import expand_source_ids_for_rag
from app.services.task_service import UnknownTaskDefinitionError, get_task_definition


ORCHESTRATION_STATUS_TRANSITIONS = {
    "planning": {"running", "failed", "cancelled"},
    "running": {"waiting_for_approval", "completed", "failed", "cancelled"},
    "waiting_for_approval": {"running", "cancelled", "failed"},
    "completed": set(),
    "failed": set(),
    "cancelled": set(),
}


class OrchestrationSessionNotFoundError(LookupError):
    pass


class InvalidOrchestrationTransitionError(ValueError):
    pass


class ProjectQaRuntimeError(RuntimeError):
    pass


class SkillPackUnavailableError(RuntimeError):
    pass


class SkillPackRuntimeError(RuntimeError):
    pass


def _codex_failure_message(exc: Exception) -> str:
    """Build a user-facing failure message that keeps the underlying detail."""
    text = str(exc).strip()
    return text[:500] if text else "Codex runtime failed."


def _is_turn_index_conflict(error: IntegrityError) -> bool:
    message = str(error.orig).lower()
    return (
        "uq_orchestration_runs_session_turn" in message
        or "orchestration_runs.session_id, orchestration_runs.turn_index" in message
    )


async def _get_authorized_session(
    *,
    db: AsyncSession,
    session_id: str,
    user: User,
) -> Session:
    workspace_id = await db.scalar(
        select(Workspace.id).where(Workspace.researcher_id == user.id)
    )
    session = await db.scalar(
        select(Session).where(
            Session.id == session_id,
            Session.workspace_id == workspace_id,
        )
    )
    if session is None:
        raise OrchestrationSessionNotFoundError("Session not found")
    return session


async def build_orchestration_context(
    *,
    db: AsyncSession,
    session_id: str,
    user: User,
    max_chunks: int = 6,
    max_memories: int = 6,
    max_text_chars: int = 1200,
    query: str | None = None,
    source_ids: list[str] | None = None,
) -> tuple[ResearchExecutionContext, dict[str, Any]]:
    """Build an authorized execution context and a safe persisted manifest."""
    session = await _get_authorized_session(db=db, session_id=session_id, user=user)
    project_source_ids = await collect_project_source_ids(
        db=db,
        project_id=session.project_id,
        user=user,
    )
    if source_ids is not None:
        requested_source_ids = await expand_source_ids_for_rag(source_ids, db)
        # Selections can go stale (a source removed from the project stays
        # linked to older sessions). Keep the authorized intersection instead
        # of failing the whole run; only reject when nothing selected is
        # still available.
        project_source_id_set = set(project_source_ids)
        available_source_ids = [
            source_id for source_id in requested_source_ids
            if source_id in project_source_id_set
        ]
        if requested_source_ids and not available_source_ids:
            raise ValueError("Selected sources are unavailable in this project")
        source_ids = available_source_ids
    else:
        source_ids = project_source_ids
    context = await build_research_execution_context(
        db=db,
        session_id=session.id,
        user_id=user.id,
        source_ids=source_ids,
        max_chunks=max_chunks,
        max_memories=max_memories,
        max_text_chars=max_text_chars,
        query=query,
    )
    manifest = {
        "source_ids": source_ids,
        "chunk_ids": [chunk.chunk_id for chunk in context.chunks],
        "memory_ids": [memory.id for memory in context.memories],
        "limits": {
            "max_chunks": max_chunks,
            "max_memories": max_memories,
            "max_text_chars": max_text_chars,
        },
    }
    return context, manifest


async def create_orchestration_run(
    *,
    db: AsyncSession,
    session_id: str,
    user: User,
    task_id: str | None = None,
    goal_message_id: str | None = None,
    plan_snapshot: dict[str, Any] | None = None,
    capability_snapshot: dict[str, Any] | None = None,
    output_contract_snapshot: dict[str, Any] | None = None,
    budget_usage: dict[str, Any] | None = None,
    context_manifest: dict[str, Any] | None = None,
    allow_task_override: bool = False,
) -> OrchestrationRun:
    """Create a planning run with a task-scoped, authorized context manifest."""
    session = await _get_authorized_session(db=db, session_id=session_id, user=user)
    effective_task_id = task_id or session.task_id
    if effective_task_id is None:
        raise ValueError("Task session is required for orchestration runs")
    if (
        task_id is not None
        and task_id != session.task_id
        and not allow_task_override
    ):
        raise ValueError("Provided task does not match session task")
    await get_task_definition(
        effective_task_id,
        db,
        project_id=session.project_id,
    )

    if context_manifest is None:
        _, context_manifest = await build_orchestration_context(
            db=db,
            session_id=session.id,
            user=user,
        )
    for _ in range(3):
        latest_turn_index = await db.scalar(
            select(func.max(OrchestrationRun.turn_index)).where(
                OrchestrationRun.session_id == session.id
            )
        )
        run = OrchestrationRun(
            session_id=session.id,
            task_id=effective_task_id,
            turn_index=(latest_turn_index or 0) + 1,
            status="planning",
            goal_message_id=goal_message_id,
            plan_snapshot=plan_snapshot or {},
            capability_snapshot=capability_snapshot or {},
            context_manifest=context_manifest,
            output_contract_snapshot=output_contract_snapshot or {},
            budget_usage=budget_usage or {},
            created_by=user.id,
        )
        try:
            async with db.begin_nested():
                db.add(run)
                await db.flush()
            return run
        except IntegrityError as exc:
            if not _is_turn_index_conflict(exc):
                raise
    raise RuntimeError("Could not allocate orchestration run turn index")


async def transition_orchestration_run(
    *,
    db: AsyncSession,
    run_id: str,
    user: User,
    target_status: str,
) -> OrchestrationRun:
    """Apply a permitted lifecycle transition to an orchestration run."""
    workspace_id = await db.scalar(
        select(Workspace.id).where(Workspace.researcher_id == user.id)
    )
    run = await db.scalar(
        select(OrchestrationRun)
        .join(Session, Session.id == OrchestrationRun.session_id)
        .where(
            OrchestrationRun.id == run_id,
            Session.workspace_id == workspace_id,
        )
    )
    if run is None:
        raise OrchestrationSessionNotFoundError("Orchestration run not found")
    allowed_statuses = ORCHESTRATION_STATUS_TRANSITIONS.get(run.status, set())
    if target_status not in allowed_statuses:
        raise InvalidOrchestrationTransitionError(
            f"Cannot transition orchestration run from {run.status} to {target_status}"
        )
    result = await db.execute(
        update(OrchestrationRun)
        .where(
            OrchestrationRun.id == run.id,
            OrchestrationRun.status == run.status,
        )
        .values(status=target_status)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise InvalidOrchestrationTransitionError(
            f"Orchestration run status changed from {run.status}"
        )
    run.status = target_status
    return run


async def execute_project_qa_run(
    *,
    db: AsyncSession,
    session_id: str,
    user: User,
    goal: str,
    source_ids: list[str] | None = None,
) -> OrchestrationRun:
    """Execute one project Q&A turn and persist its final assistant response."""
    session = await _get_authorized_session(db=db, session_id=session_id, user=user)
    if session.project_id is None:
        raise ValueError("Project Q&A requires a project session")

    context, context_manifest = await build_orchestration_context(
        db=db,
        session_id=session.id,
        user=user,
        query=goal,
        max_chunks=12,
        max_text_chars=1600,
        source_ids=source_ids,
    )
    # Include recent conversation turns so follow-up requests ("turn the above
    # into a checklist") stay continuous instead of landing in a bare context.
    history_rows = await db.scalars(
        select(Message)
        .where(Message.session_id == session.id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(10)
    )
    conversation = [
        {"role": item.role, "content": item.content[:2000]}
        for item in reversed(history_rows.all())
    ]
    run = await create_orchestration_run(
        db=db,
        session_id=session.id,
        user=user,
        task_id="project-qa",
        plan_snapshot={"mode": "project_qa"},
        output_contract_snapshot={"type": "assistant_message"},
        context_manifest=context_manifest,
        allow_task_override=True,
    )
    # Commit so the new run is visible to progress polling while it executes.
    await db.commit()
    try:
        project = await db.get(Project, session.project_id)
        project_instructions = (
            project.instructions.strip()
            if project and project.instructions
            else None
        )
        prompt = format_research_context_markdown(
            task_input={
                "task": "project-qa",
                "goal": goal,
                "conversation": conversation,
                "project_instructions": project_instructions,
                "instruction": (
                    "Answer using only the authorized project context and the "
                    "conversation history. Treat the conversation history as the "
                    "running dialogue: for follow-up requests, transform, extend, "
                    "or build on previous answers as asked, while keeping every "
                    "claim grounded in the authorized project sources. Never ask "
                    "the user to paste authorized source material. When evidence "
                    "is insufficient, state the available source boundary and "
                    "distinguish a cited work from a source whose full text is "
                    "present in the project. For questions about experimental "
                    "models, results, or mechanisms, synthesize the supplied "
                    "methods and result sections into a direct, evidence-linked "
                    "answer."
                ),
            },
            context=context,
        )

        await transition_orchestration_run(
            db=db,
            run_id=run.id,
            user=user,
            target_status="running",
        )
    except Exception as exc:
        run.status = "failed"
        run.error_code = "project_qa_prep_failed"
        run.error_message = str(exc) or "Project Q&A preparation failed"
        await db.commit()
        raise
    # Commit so the running status is visible during the codex call.
    await db.commit()
    try:
        runtime_payload = await run_codex_runtime(prompt=prompt, db=db)
        if str(runtime_payload.get("status") or "completed") != "completed":
            raise ProjectQaRuntimeError("Codex runtime did not complete the run")
        content = str(runtime_payload.get("content") or "").strip()
        if not content:
            raise ProjectQaRuntimeError("Codex runtime returned an empty response")
    except Exception as exc:
        run.status = "failed"
        run.error_code = "codex_runtime_failed"
        run.error_message = _codex_failure_message(exc)
        await db.commit()
        if isinstance(exc, ProjectQaRuntimeError):
            raise
        raise ProjectQaRuntimeError(_codex_failure_message(exc)) from exc

    final_message = Message(session_id=session.id, role="assistant", content=content)
    db.add(final_message)
    await db.flush()
    usage = runtime_payload.get("usage")
    if isinstance(usage, dict) and usage:
        run.budget_usage = usage
    run.status = "completed"
    run.final_message_id = final_message.id
    await db.commit()
    await db.refresh(run)
    return run


async def execute_skill_pack_run(
    *,
    db: AsyncSession,
    session_id: str,
    user: User,
    goal: str,
    task_id: str | None = None,
    source_ids: list[str] | None = None,
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
            include_disabled=True,
            project_id=session.project_id,
        )
    except UnknownTaskDefinitionError as exc:
        raise ValueError("Task not found") from exc
    if not task.skill_pack_id:
        raise ValueError("Task is not bound to a skill pack")

    pack = await get_current_skill_pack(db, pack_id=task.skill_pack_id)
    if pack is None or not pack.is_enabled or not task.is_enabled:
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
    # Commit so the new run is visible to progress polling while it executes.
    await db.commit()
    try:
        try:
            sandbox_cwd = await prepare_skill_run_workspace(
                db=db,
                run_id=run.id,
                pack=pack,
                session=session,
                user=user,
                source_ids=source_ids,
            )
        except FileNotFoundError as exc:
            raise SkillPackUnavailableError("Skill pack is unavailable") from exc
        if sandbox_cwd is None:
            raise SkillPackUnavailableError("Sandbox workspace is not configured")
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
        project = await db.get(Project, session.project_id)
        prompt = build_skill_pack_prompt(
            goal=goal,
            memories=memories,
            project_instructions=project.instructions if project else None,
        )

        await transition_orchestration_run(
            db=db,
            run_id=run.id,
            user=user,
            target_status="running",
        )
    except Exception as exc:
        run.status = "failed"
        run.error_code = "skill_pack_prep_failed"
        run.error_message = str(exc) or "Skill pack preparation failed"
        await db.commit()
        raise
    # Commit so the running status is visible during the codex call.
    await db.commit()
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
        run.error_message = _codex_failure_message(exc)
        await db.commit()
        if isinstance(exc, SkillPackRuntimeError):
            raise
        raise SkillPackRuntimeError(_codex_failure_message(exc)) from exc

    final_message = Message(session_id=session.id, role="assistant", content=content)
    db.add(final_message)
    await db.flush()
    usage = runtime_payload.get("usage")
    if isinstance(usage, dict) and usage:
        run.budget_usage = usage
    run.status = "completed"
    run.final_message_id = final_message.id
    await db.commit()
    await db.refresh(run)
    return run


PROGRESS_EVENT_LIMIT = 30
PROGRESS_TEXT_LIMIT = 300


def _truncate_event_strings(value: Any, limit: int = PROGRESS_TEXT_LIMIT) -> Any:
    if isinstance(value, str):
        return value if len(value) <= limit else f"{value[:limit].rstrip()}..."
    if isinstance(value, dict):
        return {key: _truncate_event_strings(item, limit) for key, item in value.items()}
    if isinstance(value, list):
        return [_truncate_event_strings(item, limit) for item in value[:10]]
    return value


def _read_progress_events(progress_path: Path) -> list[dict[str, Any]]:
    try:
        lines = progress_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    events: list[dict[str, Any]] = []
    for line in lines[-PROGRESS_EVENT_LIMIT:]:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            event = {"type": "stdout", "text": line}
        if isinstance(event, dict):
            events.append(_truncate_event_strings(event))
    return events


async def get_session_run_progress(
    *,
    db: AsyncSession,
    session_id: str,
    user: User,
) -> dict[str, Any]:
    """Return the session's latest run status plus live codex progress events."""
    session = await _get_authorized_session(db=db, session_id=session_id, user=user)
    run = await db.scalar(
        select(OrchestrationRun)
        .where(OrchestrationRun.session_id == session.id)
        .order_by(OrchestrationRun.created_at.desc())
        .limit(1)
    )
    if run is None:
        return {"run_id": None, "status": None, "events": []}
    events: list[dict[str, Any]] = []
    if settings.codex_runtime_workspace_dir:
        progress_path = (
            Path(settings.codex_runtime_workspace_dir)
            / "skill-runs"
            / run.id
            / "progress.jsonl"
        )
        events = _read_progress_events(progress_path)
    return {
        "run_id": run.id,
        "status": run.status,
        "error_code": run.error_code,
        "final_message_id": run.final_message_id,
        "events": events,
    }
