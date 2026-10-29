from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ResearchGroupRole = Literal[
    "pi",
    "postdoc",
    "phd_student",
    "assistant",
    "external_collaborator",
]


class ResearchGroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class ResearchGroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    archived: bool | None = None


class ResearchGroupResponse(BaseModel):
    id: str
    name: str
    description: str | None
    created_by: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None

    model_config = {"from_attributes": True}


class ResearchGroupMemberCreate(BaseModel):
    user_id: str
    role: ResearchGroupRole


class ResearchGroupMemberUpdate(BaseModel):
    role: ResearchGroupRole


class ResearchGroupMemberResponse(BaseModel):
    id: str
    group_id: str
    user_id: str
    role: ResearchGroupRole
    created_by: str
    created_at: datetime
    updated_at: datetime
    removed_at: datetime | None

    model_config = {"from_attributes": True}
