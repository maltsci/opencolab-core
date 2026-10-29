from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class PersonDirectionSummary(BaseModel):
    id: str
    name: str
    role: str


class PersonDirectoryEntry(BaseModel):
    id: str
    username: str
    display_name: str | None
    role: str
    bio: str | None = None
    consultation_topics: list[str] = []
    current_directions: list[PersonDirectionSummary] = []
    archived_at: datetime | None = None


class MemberProfileUpdate(BaseModel):
    bio: str | None = Field(default=None, max_length=4000)
    consultation_topics: list[str] | None = Field(default=None, max_length=20)
    show_recent_activity: bool | None = None
    last_confirmed_at: datetime | None = None
    review_due_at: datetime | None = None

    @field_validator("consultation_topics")
    @classmethod
    def normalize_topics(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        topics: list[str] = []
        normalized_topics: set[str] = set()
        for topic in value:
            normalized_topic = " ".join(topic.split())
            if not normalized_topic:
                continue
            if len(normalized_topic) > 100:
                raise ValueError("Consultation topics must be 100 characters or fewer")
            topic_key = normalized_topic.casefold()
            if topic_key not in normalized_topics:
                normalized_topics.add(topic_key)
                topics.append(normalized_topic)
        return topics


class MemberProfileResponse(BaseModel):
    bio: str | None
    consultation_topics: list[str]
    show_recent_activity: bool
    last_confirmed_at: datetime | None
    review_due_at: datetime | None
    is_stale: bool


class MemberProfileMaintenanceItemResponse(BaseModel):
    user_id: str
    display_name: str | None
    last_confirmed_at: datetime | None
    review_due_at: datetime | None
    issue: Literal["review_missing", "review_overdue"]


class MemberDirectionCreate(BaseModel):
    direction_id: str
    role: Literal["lead", "contributor", "advisor"] = "contributor"
    valid_from: datetime | None = None


class MemberDirectionHistoryEntry(PersonDirectionSummary):
    member_direction_id: str
    valid_from: datetime
    valid_until: datetime | None


class PersonDetail(PersonDirectoryEntry):
    show_recent_activity: bool
    last_confirmed_at: datetime | None
    review_due_at: datetime | None
    is_stale: bool
    direction_history: list[MemberDirectionHistoryEntry]


class PersonRecentWorkEntry(BaseModel):
    id: str
    project_id: str
    project_name: str
    action: str
    created_at: datetime


class PersonRecentWorkResponse(BaseModel):
    visible: bool
    items: list[PersonRecentWorkEntry]


class PersonResponsibilityResponse(BaseModel):
    asset_id: str
    title: str
    description: str | None
    asset_type: str


class MemberRepresentativeResourcesUpdate(BaseModel):
    asset_ids: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("asset_ids")
    @classmethod
    def reject_duplicate_asset_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("Representative resource IDs must be unique")
        return value
