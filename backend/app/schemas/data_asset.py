from datetime import datetime

from pydantic import BaseModel, Field


class DataAssetCreate(BaseModel):
    research_asset_id: str
    research_object_id: str
    data_type: str = Field(min_length=1, max_length=64)
    data_modality: str | None = Field(default=None, max_length=64)
    scientific_metadata_json: dict = Field(default_factory=dict)


class DataAssetResponse(DataAssetCreate):
    id: str
    created_by: str
    created_at: datetime

    model_config = {"from_attributes": True}
