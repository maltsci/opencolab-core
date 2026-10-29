from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


OrchestrationRunStatus = Literal[
    "planning",
    "running",
    "waiting_for_approval",
    "completed",
    "failed",
    "cancelled",
]


class OrchestrationRunCreateRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=10000)
    source_ids: list[str] | None = Field(default=None, max_length=100)


class SkillPackRunCreateRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=10000)
    task_id: str | None = None
    source_ids: list[str] | None = Field(default=None, max_length=100)


class OrchestrationRunResponse(BaseModel):
    id: str
    session_id: str
    task_id: str
    turn_index: int
    status: OrchestrationRunStatus
    goal_message_id: str | None = None
    plan_snapshot: dict[str, Any] = Field(default_factory=dict)
    capability_snapshot: dict[str, Any] = Field(default_factory=dict)
    context_manifest: dict[str, Any] = Field(default_factory=dict)
    output_contract_snapshot: dict[str, Any] = Field(default_factory=dict)
    budget_usage: dict[str, Any] = Field(default_factory=dict)
    sandbox_session_id: str | None = None
    final_message_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_by: str | None = None
    created_by_type: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
