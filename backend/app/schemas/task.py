from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TaskDefinitionBase(BaseModel):
    id: str
    version: int = 1
    name: str
    description: str
    workflow_id: str
    skill_pack_id: str | None = None
    input_schema: dict[str, Any] = Field(default_factory=dict)
    starter_prompts: list[str] = Field(default_factory=list)
    project_context_policy: dict[str, Any] = Field(default_factory=dict)
    result_presentation: dict[str, Any] = Field(default_factory=dict)
    is_enabled: bool = True
    project_ids: list[str] = Field(default_factory=list)


class TaskDefinitionCreate(TaskDefinitionBase):
    pass


class TaskDefinitionUpdate(BaseModel):
    version: int | None = None
    name: str | None = None
    description: str | None = None
    workflow_id: str | None = None
    input_schema: dict[str, Any] | None = None
    starter_prompts: list[str] | None = None
    project_context_policy: dict[str, Any] | None = None
    result_presentation: dict[str, Any] | None = None
    is_enabled: bool | None = None
    project_ids: list[str] | None = None


class TaskDefinition(TaskDefinitionBase):
    created_at: datetime | None = None
    updated_at: datetime | None = None
    is_builtin: bool = False

    model_config = {"from_attributes": True}
