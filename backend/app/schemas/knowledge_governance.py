from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class StewardAssignmentCreate(BaseModel):
    user_id: str


class GroupStewardResponse(BaseModel):
    id: str
    group_id: str
    user_id: str
    created_by: str
    created_at: datetime
    revoked_at: datetime | None

    model_config = {"from_attributes": True}


class DirectionStewardResponse(BaseModel):
    id: str
    direction_id: str
    user_id: str
    created_by: str
    created_at: datetime
    revoked_at: datetime | None

    model_config = {"from_attributes": True}


SuggestionStatus = Literal["pending", "approved", "rejected"]


class KnowledgeSuggestionCreate(BaseModel):
    target_type: Literal[
        "research_direction",
        "member_direction_link",
        "project_direction_link",
        "resource_direction_link",
        "research_object_direction_link",
        "research_direction_relation",
    ]
    target_id: str | None = None
    action: Literal["create", "update", "link", "unlink", "archive", "merge"]
    payload_json: dict = Field(default_factory=dict)
    evidence_json: dict = Field(default_factory=dict)


class SuggestionDecision(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class BulkSuggestionDecision(SuggestionDecision):
    suggestion_ids: list[str] = Field(min_length=1, max_length=100)

    @field_validator("suggestion_ids")
    @classmethod
    def reject_duplicate_suggestion_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("Suggestion IDs must be unique")
        return value


class KnowledgeReviewCapabilityResponse(BaseModel):
    can_review: bool


class KnowledgeSuggestionResponse(BaseModel):
    id: str
    target_type: str
    target_id: str | None
    action: str
    payload_json: dict
    evidence_json: dict
    status: SuggestionStatus
    submitted_by: str | None
    submitted_by_type: str
    reviewer_id: str | None
    decision_reason: str | None
    decided_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class KnowledgeSuggestionAuditResponse(BaseModel):
    id: str
    entity_type: str
    entity_id: str
    action: str
    actor_id: str | None
    suggestion_id: str | None
    before_json: dict
    after_json: dict
    created_at: datetime

    model_config = {"from_attributes": True}


class KnowledgeInboxResponse(BaseModel):
    review_items: list[KnowledgeSuggestionResponse]
    decision_items: list[KnowledgeSuggestionResponse]
    unread_decision_count: int


class KnowledgeInboxDecisionsReadResponse(BaseModel):
    marked_count: int


class KnowledgeHealthResponse(BaseModel):
    member_profile_review_count: int
    direction_review_count: int
    resource_review_count: int
    pending_suggestion_count: int
