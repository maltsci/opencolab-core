from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.sessions import _get_session_for_user
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.message import Message
from app.models.trace import ResearchTrace
from app.models.user import User
from app.schemas.trace import ResearchTraceResponse

router = APIRouter(prefix="/sessions", tags=["research-threads"])


@router.get("/{session_id}/trace", response_model=list[ResearchTraceResponse])
async def list_session_traces(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_session_for_user(session_id, user, db)

    result = await db.execute(
        select(ResearchTrace)
        .outerjoin(Message, Message.id == ResearchTrace.message_id)
        .where(ResearchTrace.session_id == session_id)
        .order_by(
            func.coalesce(Message.created_at, ResearchTrace.created_at).desc(),
            ResearchTrace.created_at.desc(),
        )
    )
    return [
        ResearchTraceResponse.model_validate(trace)
        for trace in result.scalars().all()
    ]
