from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class AssetMemberCreate(BaseModel):
    role: Literal["primary", "package", "extracted", "index", "attachment"]
    content_mode: Literal["managed", "external", "generated"]
    position: int = Field(ge=0)
    normalized_path: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    media_type: str | None = None
    format: str = Field(min_length=1, max_length=32)
    size_bytes: int | None = Field(default=None, ge=0)
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    managed_source_id: str | None = None
    external_reference_ciphertext: str | None = None
    external_metadata_json: dict = Field(default_factory=dict)
    external_handoff_json: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_content_reference(self) -> "AssetMemberCreate":
        if self.content_mode in {"managed", "generated"}:
            if self.managed_source_id is None or self.external_reference_ciphertext:
                raise ValueError("Managed members require one managed source")
        elif (
            self.external_reference_ciphertext is None
            or self.managed_source_id is not None
        ):
            raise ValueError("External members require one protected reference")
        return self


class AssetContentMemberResponse(AssetMemberCreate):
    id: str
    asset_revision_id: str

    model_config = {"from_attributes": True}


class AssetRevisionResponse(BaseModel):
    id: str
    research_asset_id: str
    revision_number: int
    processing_state: str
    manifest_sha256: str | None
    change_summary: str | None
    created_by: str
    created_at: datetime
    sealed_at: datetime | None

    model_config = {"from_attributes": True}
