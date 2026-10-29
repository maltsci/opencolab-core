from datetime import datetime
from typing import Any

from pydantic import BaseModel


class SourceExtractionResponse(BaseModel):
    id: str
    source_id: str
    status: str
    document_type: str | None = None
    schema_version: str = "v1"
    structured_json: dict[str, Any]
    error_message: str | None = None
    metadata_status: str = "not_applicable"
    metadata_attempts: int = 0
    metadata_next_attempt_at: datetime | None = None
    metadata_checked_at: datetime | None = None
    metadata_error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
