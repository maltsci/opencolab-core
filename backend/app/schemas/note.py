from datetime import datetime

from pydantic import BaseModel

from app.schemas.source import ShareInfo


class NoteCreate(BaseModel):
    session_id: str
    message_id: str | None = None
    content: str


class NoteUpdate(BaseModel):
    content: str


class NoteResponse(BaseModel):
    id: str
    session_id: str
    message_id: str | None
    content: str
    created_at: datetime
    owner_id: str | None = None
    owner_name: str | None = None
    share: ShareInfo | None = None
    is_shared: bool = False
    can_edit: bool = False

    model_config = {"from_attributes": True}
