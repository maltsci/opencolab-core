from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.sessions import _get_session_for_user
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.agent_run import AgentRun
from app.models.message import Message
from app.models.trace import ResearchTrace
from app.models.user import User
from app.schemas.agent import AgentRunResponse
from app.schemas.message import MessageCreate, MessageResponse

router = APIRouter(tags=["messages"])


@router.get(
    "/sessions/{session_id}/messages", response_model=list[MessageResponse]
)
async def list_messages(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_session_for_user(session_id, user, db)

    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at, Message.id)
    )
    messages = result.scalars().all()
    if not messages:
        return []

    message_ids = [message.id for message in messages]
    trace_result = await db.execute(
        select(ResearchTrace).where(
            ResearchTrace.message_id.in_(message_ids),
            ResearchTrace.agent_run_id.is_not(None),
        )
    )
    traces = trace_result.scalars().all()
    agent_run_ids = list(
        {
            trace.agent_run_id
            for trace in traces
            if trace.agent_run_id
        }
    )

    agent_run_map: dict[str, AgentRunResponse] = {}
    if agent_run_ids:
        agent_run_result = await db.execute(
            select(AgentRun)
            .options(selectinload(AgentRun.traces))
            .where(AgentRun.id.in_(agent_run_ids))
        )
        agent_run_map = {
            item.id: AgentRunResponse.model_validate(item)
            for item in agent_run_result.scalars().all()
        }

    trace_by_message_id = {
        trace.message_id: trace
        for trace in traces
        if trace.message_id
    }

    response_items: list[MessageResponse] = []
    for item in messages:
        trace = trace_by_message_id.get(item.id)
        agent_run = (
            agent_run_map.get(trace.agent_run_id)
            if trace and trace.agent_run_id
            else None
        )
        response_items.append(
            MessageResponse(
                id=item.id,
                session_id=item.session_id,
                role=item.role,
                content=item.content,
                created_at=item.created_at,
                agent_run=agent_run,
            )
        )

    return response_items


@router.post(
    "/sessions/{session_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_message(
    session_id: str,
    body: MessageCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_session_for_user(session_id, user, db)

    # Save user message (actual LLM response is handled via WebSocket)
    message = Message(session_id=session_id, role="user", content=body.content)
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return MessageResponse.model_validate(message)
