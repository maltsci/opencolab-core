from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ResearchTraceResponse(BaseModel):
    id: str
    session_id: str
    message_id: str | None = None
    agent_run_id: str | None = None
    workflow_run_id: str | None = None
    inputs: dict[str, Any] = Field(validation_alias="inputs_json")
    retrieval: list[dict[str, Any]] = Field(validation_alias="retrieval_json")
    citations: list[dict[str, Any]] = Field(validation_alias="citations_json")
    summary_steps: list[str] = Field(validation_alias="summary_steps_json")
    created_at: datetime | None = None

    model_config = {"from_attributes": True}
