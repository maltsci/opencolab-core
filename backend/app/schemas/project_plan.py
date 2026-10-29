from datetime import date, datetime

from pydantic import BaseModel, Field

PLAN_PRIORITIES = {"low", "medium", "high"}
PLAN_STATUSES = {"todo", "in_progress", "done"}


class PlanCreate(BaseModel):
    title: str = Field(max_length=200)
    content: str | None = None
    start_date: date | None = None
    due_date: date | None = None
    priority: str = "medium"
    tags: list[str] = []
    assignee_id: str | None = None


class PlanUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    content: str | None = None
    start_date: date | None = None
    due_date: date | None = None
    priority: str | None = None
    tags: list[str] | None = None
    assignee_id: str | None = None
    status: str | None = None


class PlanResponse(BaseModel):
    id: str
    project_id: str
    title: str
    content: str | None
    start_date: date | None
    due_date: date | None
    priority: str
    tags: list[str]
    assignee_id: str | None
    assignee_name: str | None = None
    status: str
    created_by: str | None
    creator_name: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
