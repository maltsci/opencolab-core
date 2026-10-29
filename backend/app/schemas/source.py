from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator


class ShareInfo(BaseModel):
    shared_by: str | None = None
    shared_by_name: str | None = None
    scope: str
    project_id: str | None = None
    permission: str
    shared_at: datetime


class ShareSourceRequest(BaseModel):
    scope: str  # "all" or "project"
    project_id: str | None = None  # required when scope="project"
    permission: str = "read"  # "read" or "readwrite"


class UpdateShareRequest(BaseModel):
    scope: str | None = None
    project_id: str | None = None
    permission: str | None = None


class SourceResponse(BaseModel):
    id: str
    type: str
    name: str
    content_hash: str | None = None
    created_at: datetime
    member_count: int | None = None  # Only for type=group: number of direct members
    processing_state: str = "ready"
    extraction_status: str | None = None
    progress: int = 0
    error_message: str | None = None
    meta_info: dict | None = None
    owner_id: str | None = None
    owner_name: str | None = None
    share: ShareInfo | None = None
    is_shared: bool = False
    can_edit: bool = False
    duplicate_info: "DuplicateUploadInfo | None" = None

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def _coerce_share(cls, data: Any) -> Any:
        """When building from an ORM Source object, convert to a plain dict
        to avoid lazy-load issues (MissingGreenlet) in async context.
        The 'share' relationship may not be loaded; accessing it without
        checking would trigger a lazy load that fails in async."""
        if not isinstance(data, dict):
            # Use SQLAlchemy inspection to safely check loaded attributes
            try:
                from sqlalchemy import inspect as sa_inspect
                insp = sa_inspect(data)
                loaded = insp.dict
            except Exception:
                return data

            attrs = {}
            for field in ("id", "type", "name", "content_hash", "created_at",
                          "processing_state", "progress", "error_message",
                          "meta_info", "owner_id"):
                attrs[field] = getattr(data, field, None)

            extraction = loaded.get("extraction")
            attrs["extraction_status"] = getattr(extraction, "status", None) if extraction else None

            # Only access 'share' if the relationship is already loaded
            if "share" in loaded and loaded["share"] is not None:
                # Will be overridden by build_source_response_fields
                attrs["share"] = None
            else:
                attrs["share"] = None

            return attrs
        return data


class AvailableSourceResponse(BaseModel):
    category: str
    source: SourceResponse


class DuplicateUploadLocation(BaseModel):
    location_type: str
    label: str
    asset_id: str | None = None
    project_id: str | None = None
    visibility_scope: str | None = None
    can_use: bool = False


class DuplicateUploadInfo(BaseModel):
    code: str = "duplicate_source"
    existing_source_id: str
    content_hash: str | None = None
    can_use_existing: bool = False
    can_request_access: bool = False
    inaccessible_count: int = 0
    locations: list[DuplicateUploadLocation] = []


class LinkSourceRequest(BaseModel):
    source_id: str


class CreateGroupRequest(BaseModel):
    name: str
    # When set, the new collection is materialized as an asset of this project.
    project_id: str | None = None


class UpdateSourceRequest(BaseModel):
    name: str


class UpdateSessionSourceRequest(BaseModel):
    display_name: str


class ZipUploadResponse(BaseModel):
    sources: list[SourceResponse]
    groups: list[SourceResponse]
    errors: list[str] = []
    created_source_ids: list[str] = Field(default_factory=list, exclude=True)


class AddMemberRequest(BaseModel):
    child_id: str


class SourceMemberResponse(BaseModel):
    id: str
    parent_id: str
    child_id: str
    added_at: datetime
    child: SourceResponse | None = None  # Populated when listing members

    model_config = {"from_attributes": True}
