from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ResearchObjectCreate(BaseModel):
    session_id: str
    message_id: str | None = None
    type: Literal["hypothesis", "discussion"]
    title: str | None = Field(default=None, max_length=500)
    content: str | None = None
    content_json: dict = Field(default_factory=dict)


class ResearchObjectUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    content: str | None = None


class ResearchObjectDirectionCreateSuggestionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("name", "reason")
    @classmethod
    def require_nonempty_text(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Value is required")
        return value


class ResearchObjectResponse(BaseModel):
    id: str
    session_id: str | None = None
    message_id: str | None = None
    type: str
    title: str | None
    content: str | None
    content_json: dict
    created_by: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
