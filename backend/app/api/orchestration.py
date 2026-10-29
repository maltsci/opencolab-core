from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.orchestration_run import OrchestrationRun
from app.models.session import Session
from app.models.user import User
from app.schemas.orchestration import (
    OrchestrationRunCreateRequest,
    OrchestrationRunResponse,
    SkillPackRunCreateRequest,
)
from app.services.orchestration_service import (
    OrchestrationSessionNotFoundError,
    ProjectQaRuntimeError,
    SkillPackRuntimeError,
    SkillPackUnavailableError,
    execute_project_qa_run,
    execute_skill_pack_run,
    get_session_run_progress,
)

router = APIRouter(tags=["orchestration-runs"])


async def _get_orchestration_run_for_user(
    *,
    run_id: str,
    user: User,
    db: AsyncSession,
) -> OrchestrationRun:
    run = await db.scalar(
        select(OrchestrationRun)
        .join(Session, Session.id == OrchestrationRun.session_id)
        .where(
            OrchestrationRun.id == run_id,
            Session.workspace_id == user.workspace.id,
        )
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Orchestration run not found")
    return run


@router.post(
    "/sessions/{session_id}/orchestration-runs/project-qa",
    response_model=OrchestrationRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def run_project_qa(
    session_id: str,
    body: OrchestrationRunCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        run = await execute_project_qa_run(
            db=db,
            session_id=session_id,
            user=user,
            goal=body.goal,
            source_ids=body.source_ids,
        )
    except OrchestrationSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ProjectQaRuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc) or "Codex runtime failed.",
        ) from exc
    return OrchestrationRunResponse.model_validate(run)


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
            source_ids=body.source_ids,
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
            detail=str(exc) or "Codex runtime failed.",
        ) from exc
    return OrchestrationRunResponse.model_validate(run)


@router.get(
    "/sessions/{session_id}/orchestration-runs/progress",
)
async def get_run_progress(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await get_session_run_progress(db=db, session_id=session_id, user=user)
    except OrchestrationSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc


@router.get(
    "/sessions/{session_id}/orchestration-runs",
    response_model=list[OrchestrationRunResponse],
)
async def list_session_orchestration_runs(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(OrchestrationRun)
        .join(Session, Session.id == OrchestrationRun.session_id)
        .where(
            OrchestrationRun.session_id == session_id,
            Session.workspace_id == user.workspace.id,
        )
        .order_by(OrchestrationRun.turn_index.desc())
    )
    return [
        OrchestrationRunResponse.model_validate(run)
        for run in result.scalars().all()
    ]


@router.get(
    "/orchestration-runs/{run_id}",
    response_model=OrchestrationRunResponse,
)
async def get_orchestration_run(
    run_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    run = await _get_orchestration_run_for_user(run_id=run_id, user=user, db=db)
    return OrchestrationRunResponse.model_validate(run)
