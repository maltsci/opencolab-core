from datetime import datetime

from pydantic import BaseModel


class ActivityResponse(BaseModel):
    id: str
    project_id: str
    actor_id: str | None
    actor_name: str | None = None
    action: str
    target_type: str | None
    target_id: str | None
    target_title: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
