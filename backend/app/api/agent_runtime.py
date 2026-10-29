from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.agent_runtime import (
    CodexRuntimeRunRequest,
    CodexRuntimeRunResponse,
    CodexRuntimeStatusResponse,
)
from app.services.codex_runtime import (
    get_codex_runtime_status,
    run_codex_runtime,
)

router = APIRouter(prefix="/agent-runtime", tags=["agent-runtime"])


@router.get("/codex/status", response_model=CodexRuntimeStatusResponse)
async def get_codex_status(
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return CodexRuntimeStatusResponse.model_validate(
        await get_codex_runtime_status(db)
    )


@router.post("/codex/run", response_model=CodexRuntimeRunResponse)
async def run_codex(
    body: CodexRuntimeRunRequest,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        payload = await run_codex_runtime(
            prompt=body.prompt,
            cwd=body.cwd,
            sandbox=body.sandbox,
            db=db,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Codex runtime failed: {exc}",
        ) from exc

    return CodexRuntimeRunResponse(
        status=str(payload.get("status") or "completed"),
        content=str(payload.get("content") or ""),
        raw_events=payload.get("raw_events") if isinstance(payload.get("raw_events"), list) else [],
    )
