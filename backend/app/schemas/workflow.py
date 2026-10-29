from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.research_object import ResearchObjectResponse
from app.schemas.research_object_relation import (
    ResearchObjectRelationResponse,
    ResearchRelationType,
)
SkillStepType = Literal["skill", "llm", "tool", "human_checkpoint"]

WorkflowRunStatus = Literal[
    "pending",
    "running",
    "waiting_for_checkpoint",
    "completed",
    "failed",
    "cancelled",
]

StepRunStatus = Literal[
    "pending",
    "running",
    "completed",
    "failed",
    "skipped",
    "waiting_for_checkpoint",
]


class WorkflowStepDefinition(BaseModel):
    id: str
    type: SkillStepType
    ref: str
    depends_on: list[str] = Field(default_factory=list)
    retry_policy: dict[str, Any] = Field(default_factory=dict)
    validation_rule: str | None = None
    output_key: str


class WorkflowDefinition(BaseModel):
    id: str
    version: int = 1
    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    steps: list[WorkflowStepDefinition]
    checkpoint_policy: dict[str, Any] = Field(default_factory=dict)
    writeback_policy: dict[str, Any] = Field(default_factory=dict)

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def validate_unique_step_ids(self) -> "WorkflowDefinition":
        step_ids = [step.id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("workflow step ids must be unique")
        return self


class WorkflowRunCreateRequest(BaseModel):
    session_id: str
    input: dict[str, Any] = Field(default_factory=dict)
    replace_message_id: str | None = None


class StepRunResponse(BaseModel):
    id: str
    workflow_run_id: str
    step_id: str
    step_type: str
    ref: str
    status: StepRunStatus
    input_payload: dict[str, Any] = Field(default_factory=dict)
    output_payload: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    attempt_count: int
    started_at: datetime | None = None
    finished_at: datetime | None = None

    model_config = {"from_attributes": True}


class WorkflowRunResponse(BaseModel):
    id: str
    workflow_id: str
    workflow_version: int
    session_id: str
    status: WorkflowRunStatus
    input_payload: dict[str, Any] = Field(default_factory=dict)
    output_payload: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    created_by: str | None = None
    created_by_type: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class WorkflowRunSaveMemoryRelationRequest(BaseModel):
    enabled: bool = False
    relation_type: ResearchRelationType | None = None
    target_object_id: str | None = None
    note: str | None = None

    @model_validator(mode="after")
    def validate_when_enabled(self) -> "WorkflowRunSaveMemoryRelationRequest":
        if self.enabled and (
            self.relation_type is None or not self.target_object_id
        ):
            raise ValueError(
                "relation_type and target_object_id are required when relation is enabled"
            )
        return self


class WorkflowRunSaveMemoryRequest(BaseModel):
    type: Literal["hypothesis", "discussion"]
    title: str | None = Field(default=None, max_length=500)
    content: str
    relation: WorkflowRunSaveMemoryRelationRequest = Field(
        default_factory=WorkflowRunSaveMemoryRelationRequest
    )


class WorkflowRunSaveMemoryResponse(BaseModel):
    research_object: ResearchObjectResponse
    relation: ResearchObjectRelationResponse | None = None
