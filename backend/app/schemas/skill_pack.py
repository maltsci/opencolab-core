from datetime import datetime

from pydantic import BaseModel, computed_field


class SkillPackResponse(BaseModel):
    id: str
    version: int
    name: str
    description: str
    is_enabled: bool
    created_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}

    @computed_field
    @property
    def task_id(self) -> str:
        return f"skill-pack-{self.id}"


class SkillPackUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    is_enabled: bool | None = None
