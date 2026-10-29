from datetime import datetime

from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    title: str | None = None
    project_id: str | None = None
    task_id: str | None = Field(default=None, max_length=100)
    tag_ids: list[str] | None = None


class SessionUpdate(BaseModel):
    title: str | None = None
    tag_ids: list[str] | None = None


class SessionResponse(BaseModel):
    id: str
    workspace_id: str
    project_id: str | None = None
    title: str | None
    task_id: str | None = None
    conversation_summary: str | None = None
    created_at: datetime
    message_count: int = 0
    owner_id: str | None = None
    owner_name: str | None = None

    model_config = {"from_attributes": True}
