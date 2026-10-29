from pydantic import BaseModel

from app.schemas.people import PersonDirectoryEntry


class ProjectCreate(BaseModel):
    name: str
    description: str | None = None
    instructions: str | None = None
    research_group_id: str | None = None
    task_ids: list[str] = []


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    instructions: str | None = None
    research_group_id: str | None = None
    task_ids: list[str] | None = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: str | None
    instructions: str | None = None
    task_ids: list[str] = []
    archived: bool
    research_group_id: str | None = None
    member_count: int
    owner_name: str | None = None
    is_owner: bool = False

    model_config = {"from_attributes": True}


class MemberAdd(BaseModel):
    researcher_id: str
    role: str = "member"


class MemberUpdate(BaseModel):
    role: str


class MemberResponse(BaseModel):
    id: str
    researcher_id: str
    role: str
    username: str | None = None
    display_name: str | None = None

    model_config = {"from_attributes": True}


class ProjectKnowledgeDirectionResponse(BaseModel):
    id: str
    name: str
    summary: str | None


class ProjectKnowledgeContextResponse(BaseModel):
    members: list[PersonDirectoryEntry]
    directions: list[ProjectKnowledgeDirectionResponse]


class BatchProjectIds(BaseModel):
    project_ids: list[str]


class BatchShareRequest(BaseModel):
    project_ids: list[str]
    researcher_ids: list[str]


class BatchResult(BaseModel):
    succeeded: list[str]
    failed: list[str]


class OwnerResponse(BaseModel):
    id: str
    username: str
    display_name: str | None = None
