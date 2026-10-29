from datetime import datetime

from pydantic import BaseModel

from app.schemas.agent import AgentRunResponse


class MessageCreate(BaseModel):
    content: str
    source_ids: list[str] | None = None


class MessageResponse(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    created_at: datetime
    agent_run: AgentRunResponse | None = None

    model_config = {"from_attributes": True}
