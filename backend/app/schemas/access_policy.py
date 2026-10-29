from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.core.governance import Capability


class AccessPolicyCreate(BaseModel):
    research_asset_id: str
    asset_revision_id: str | None = None
    applies_to_future_revisions: bool = False
    subject_type: Literal["user", "research_group", "project", "group_role"]
    subject_id: str | None = None
    group_role: str | None = None
    required_project_id: str | None = None
    required_agreement_id: str | None = None
    capabilities_json: list[Capability] = Field(min_length=1)
    effect: Literal["allow", "deny"] = "allow"
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    priority: int = 0
    enabled: bool = True

    @model_validator(mode="after")
    def validate_revision_scope(self) -> "AccessPolicyCreate":
        if self.asset_revision_id and self.applies_to_future_revisions:
            raise ValueError(
                "Revision policy cannot apply to future revisions"
            )
        if self.valid_from and self.valid_until and self.valid_until <= self.valid_from:
            raise ValueError("Policy validity range must move forward")
        return self


class AccessPolicyResponse(AccessPolicyCreate):
    id: str
    created_by: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DataUseAgreementCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    owning_group_id: str
    status: Literal["draft", "active", "expired", "revoked"] = "draft"
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    allowed_project_id: str | None = None
    allowed_research_group_id: str | None = None
    allowed_capabilities_json: list[Capability] = Field(min_length=1)
    reference: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_time_range(self) -> "DataUseAgreementCreate":
        if self.valid_from and self.valid_until and self.valid_until <= self.valid_from:
            raise ValueError("Agreement validity range must move forward")
        return self


class DataUseAgreementResponse(DataUseAgreementCreate):
    id: str
    created_by: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
