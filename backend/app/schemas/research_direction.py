from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


DirectionStatus = Literal["active", "archived", "merged"]


class ResearchDirectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    summary: str | None = None
    background: str | None = None
    scope: str | None = None
    owner_id: str | None = None


class ResearchDirectionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    summary: str | None = None
    background: str | None = None
    scope: str | None = None
    owner_id: str | None = None
    last_confirmed_at: datetime | None = None
    review_due_at: datetime | None = None


class ResearchDirectionMerge(BaseModel):
    target_direction_id: str
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason")
    @classmethod
    def require_nonempty_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Merge reason is required")
        return value


class ResearchDirectionResponse(BaseModel):
    id: str
    name: str
    summary: str | None
    background: str | None
    scope: str | None
    status: DirectionStatus
    owner_id: str | None
    merged_into_id: str | None
    last_confirmed_at: datetime | None
    review_due_at: datetime | None
    created_by: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ResearchDirectionCapabilitiesResponse(BaseModel):
    can_maintain: bool


class DirectionMaintenanceItemResponse(BaseModel):
    direction_id: str
    name: str
    last_confirmed_at: datetime | None
    review_due_at: datetime | None
    issue: Literal["review_missing", "review_overdue"]


class ResearchDirectionPage(BaseModel):
    items: list[ResearchDirectionResponse]
    next_cursor: str | None = None


class DirectionResourceResponse(BaseModel):
    asset_id: str
    title: str
    description: str | None
    asset_type: str
    steward_name: str | None
    purpose: str | None


class DirectionResearchObjectResponse(BaseModel):
    asset_id: str
    research_object_id: str
    title: str | None
    object_type: str
    relation_type: str
    reason: str | None


class DirectionProjectCreate(BaseModel):
    project_id: str
    reason: str | None = Field(default=None, max_length=2000)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class DirectionProjectResponse(BaseModel):
    project_id: str
    name: str
    description: str | None
    reason: str | None
    created_at: datetime


class DirectionActivityResponse(BaseModel):
    id: str
    project_id: str
    project_name: str
    action: str
    created_at: datetime
    is_pinned: bool = False


class DirectionActivityPresentationUpdate(BaseModel):
    presentation: Literal["normal", "pinned", "hidden"]


class DirectionActivityPresentationResponse(BaseModel):
    activity_id: str
    presentation: Literal["normal", "pinned", "hidden"]


class DirectionLearningResourcesUpdate(BaseModel):
    asset_ids: list[str] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def require_unique_asset_ids(self) -> "DirectionLearningResourcesUpdate":
        if len(set(self.asset_ids)) != len(self.asset_ids):
            raise ValueError("Learning resources must be unique")
        return self


class DirectionLearningResourceResponse(BaseModel):
    asset_id: str
    title: str
    description: str | None
    asset_type: str
    steward_name: str | None
    purpose: str | None
    learning_order: int


class DirectionRepresentativeResourcesUpdate(DirectionLearningResourcesUpdate):
    pass


class DirectionMemberResponse(BaseModel):
    id: str
    username: str
    display_name: str | None
    role: str
    direction_role: str


class DirectionRelationCreate(BaseModel):
    target_direction_id: str
    reason: str = Field(min_length=1, max_length=2000)
    evidence_json: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_nonempty_reason(self) -> "DirectionRelationCreate":
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValueError("Relation reason is required")
        return self


class DirectionRelationResponse(BaseModel):
    id: str
    direction_a_id: str
    direction_b_id: str
    relation_type: Literal["related"]
    reason: str
    evidence_json: dict
    created_by: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ResearchObjectDirectionRequest(BaseModel):
    research_object_id: str
    relation_type: Literal["belongs_to", "informs"] = "belongs_to"
    reason: str = Field(min_length=1, max_length=2000)
