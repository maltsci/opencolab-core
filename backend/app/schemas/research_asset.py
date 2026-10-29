import re
from datetime import datetime
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

from app.schemas.source import DuplicateUploadInfo

VisibilityScope = Literal["private", "project", "lab_private", "lab_public"]
PublicationStatus = Literal["active", "withdrawn"]

_CREDENTIAL_PATTERNS = (
    re.compile(
        r"\b(?:password|passwd|api[_ -]?key|access[_ -]?token|secret(?:[_ -]?key)?)\s*[:=]",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:token|api[_-]?key)=[^&\s]+", re.IGNORECASE),
    re.compile(r"-----BEGIN (?:OPENSSH|RSA|EC|DSA) PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
)


def _normalize_catalog_text(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if any(pattern.search(value) for pattern in _CREDENTIAL_PATTERNS):
        raise ValueError("Credentials cannot be stored in the resource catalog")
    return value or None


def _normalize_request_url(value: str | None) -> str | None:
    value = _normalize_catalog_text(value)
    if value is None:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Request URL must use http or https")
    return value


class ResearchAssetResponse(BaseModel):
    id: str
    asset_type: str
    asset_category: str = "uploaded_material"
    title: str
    title_source: str = "filename"
    title_locked: bool = False
    description: str | None = None
    source_id: str | None = None
    research_object_id: str | None = None
    owner_id: str | None = None
    owner_name: str | None = None
    owning_group_id: str | None = None
    owning_group_name: str | None = None
    steward_user_id: str | None = None
    classification: str = "confidential"
    catalog_status: str = "published"
    lifecycle_status: str = "active"
    governance_review_status: str = "pending"
    catalog_metadata_json: dict = Field(default_factory=dict)
    protected_metadata_json: dict = Field(default_factory=dict)
    current_revision_id: str | None = None
    catalog_published_at: datetime | None = None
    catalog_withdrawn_at: datetime | None = None
    origin_project_id: str | None = None
    origin_project_name: str | None = None
    origin_session_id: str | None = None
    visibility_scope: str
    publication_status: str
    published_by: str | None = None
    published_by_name: str | None = None
    published_at: datetime | None = None
    withdrawn_at: datetime | None = None
    withdrawal_reason: str | None = None
    deleted_at: datetime | None = None
    deleted_by: str | None = None
    delete_reason: str | None = None
    metadata_json: dict
    created_at: datetime
    updated_at: datetime
    is_linked_to_project: bool = False
    can_publish: bool = False
    can_grant_training: bool = False
    can_delete: bool = False
    can_withdraw: bool = False
    can_change_classification: bool = False
    can_preview_content: bool = False
    can_request_access: bool = False
    active_access_request_id: str | None = None
    active_access_request_status: str | None = None
    active_access_grant_valid_until: datetime | None = None
    withdrawn_warning: str | None = None
    source_processing_state: str | None = None
    source_processing_progress: int | None = None
    source_error_message: str | None = None
    source_type: str | None = None
    source_meta_info: dict | None = None
    original_filename: str | None = None
    metadata_status: str = "not_applicable"
    bibliographic_summary: dict = Field(default_factory=dict)
    duplicate_info: DuplicateUploadInfo | None = None

    model_config = {"from_attributes": True}


class ResearchAssetCatalogResponse(BaseModel):
    id: str | None = None
    title: str
    title_source: str = "filename"
    title_locked: bool = False
    description: str | None = None
    asset_type: str
    asset_category: str
    origin_project_id: str | None = None
    origin_session_id: str | None = None
    owning_group_id: str | None = None
    steward_user_id: str | None = None
    classification: str
    catalog_status: str
    lifecycle_status: str
    governance_review_status: str
    catalog_metadata_json: dict = Field(default_factory=dict)
    current_revision_id: str | None = None
    catalog_published_at: datetime | None = None
    catalog_withdrawn_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ResearchAssetCatalogListResponse(ResearchAssetCatalogResponse):
    visibility_scope: str
    publication_status: str
    owner_name: str | None = None
    has_source: bool = False
    source_processing_state: str | None = None
    source_processing_progress: int | None = None
    source_type: str | None = None
    source_meta_info: dict | None = None
    original_filename: str | None = None
    metadata_status: str = "not_applicable"
    bibliographic_summary: dict = Field(default_factory=dict)
    published_at: datetime | None = None
    withdrawn_at: datetime | None = None
    deleted_at: datetime | None = None
    is_linked_to_project: bool = False
    can_publish: bool = False
    can_grant_training: bool = False
    can_delete: bool = False
    can_withdraw: bool = False
    can_change_classification: bool = False
    can_preview_content: bool = False
    can_request_access: bool = False
    active_access_request_id: str | None = None
    active_access_request_status: str | None = None
    active_access_grant_valid_until: datetime | None = None
    withdrawn_warning: str | None = None


class ManualCatalogAssetCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    asset_type: Literal[
        "dataset",
        "code_repository",
        "model_weight",
        "gpu",
        "external_reference",
    ]
    description: str | None = Field(default=None, max_length=2000)
    visibility_scope: Literal["lab_private", "lab_public"] = "lab_public"

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        value = _normalize_catalog_text(" ".join(value.split()))
        if not value:
            raise ValueError("Resource title is required")
        return value

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return _normalize_catalog_text(value)


class ResourceProfileUpdate(BaseModel):
    purpose: str | None = Field(default=None, max_length=2000)
    suitable_for: str | None = Field(default=None, max_length=2000)
    limitations: str | None = Field(default=None, max_length=2000)
    access_instructions: str | None = Field(default=None, max_length=2000)
    request_url: str | None = Field(default=None, max_length=2000)
    gpu_configuration: str | None = Field(default=None, max_length=2000)
    gpu_login_instructions: str | None = Field(default=None, max_length=2000)
    gpu_maintenance_note: str | None = Field(default=None, max_length=2000)
    code_repository_url: str | None = Field(default=None, max_length=2000)
    code_runtime_environment: str | None = Field(default=None, max_length=2000)
    code_license: str | None = Field(default=None, max_length=500)
    code_entrypoint: str | None = Field(default=None, max_length=1000)
    model_weight_source: str | None = Field(default=None, max_length=2000)
    model_weight_version: str | None = Field(default=None, max_length=500)
    model_weight_framework: str | None = Field(default=None, max_length=2000)
    model_weight_license: str | None = Field(default=None, max_length=500)
    model_weight_usage_instructions: str | None = Field(default=None, max_length=2000)
    dataset_source: str | None = Field(default=None, max_length=2000)
    dataset_version: str | None = Field(default=None, max_length=500)
    dataset_format: str | None = Field(default=None, max_length=1000)
    dataset_update_frequency: str | None = Field(default=None, max_length=1000)
    last_confirmed_at: datetime | None = None
    review_due_at: datetime | None = None

    @field_validator(
        "purpose",
        "suitable_for",
        "limitations",
        "access_instructions",
        "gpu_configuration",
        "gpu_login_instructions",
        "gpu_maintenance_note",
        "code_repository_url",
        "code_runtime_environment",
        "code_license",
        "code_entrypoint",
        "model_weight_source",
        "model_weight_version",
        "model_weight_framework",
        "model_weight_license",
        "model_weight_usage_instructions",
        "dataset_source",
        "dataset_version",
        "dataset_format",
        "dataset_update_frequency",
    )
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return _normalize_catalog_text(value)

    @field_validator("request_url")
    @classmethod
    def normalize_request_url(cls, value: str | None) -> str | None:
        return _normalize_request_url(value)


class BibliographicMetadataUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=500)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        normalized = _normalize_catalog_text(" ".join(value.split()))
        if not normalized:
            raise ValueError("Paper title is required")
        return normalized


class BibliographicCandidateApply(BaseModel):
    candidate_index: int = Field(ge=0)


class BibliographicMetadataResponse(BaseModel):
    asset_id: str
    title: str
    original_filename: str | None = None
    title_source: str
    title_locked: bool
    metadata_status: str
    metadata_checked_at: datetime | None = None
    metadata_error: str | None = None
    catalog_metadata: dict = Field(default_factory=dict)
    keywords: list[str] = Field(default_factory=list)
    local_title_candidate: dict | None = None
    identifier_candidates: list[dict] = Field(default_factory=list)
    provider_candidates: list[dict] = Field(default_factory=list)
    resolution: dict = Field(default_factory=dict)
    can_update: bool = False


class ResourceDirectionLinkCreate(BaseModel):
    direction_id: str
    purpose: str | None = Field(default=None, max_length=2000)

    @field_validator("purpose")
    @classmethod
    def normalize_optional_purpose(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class ResourceDirectionLinkResponse(BaseModel):
    id: str
    direction_id: str
    direction_name: str
    direction_status: str
    purpose: str | None
    created_at: datetime


class ResourceProfileResponse(BaseModel):
    asset_id: str
    steward_user_id: str | None
    steward_name: str | None
    purpose: str | None
    suitable_for: str | None
    limitations: str | None
    access_instructions: str | None
    request_url: str | None
    gpu_configuration: str | None
    gpu_login_instructions: str | None
    gpu_maintenance_note: str | None
    code_repository_url: str | None
    code_runtime_environment: str | None
    code_license: str | None
    code_entrypoint: str | None
    model_weight_source: str | None
    model_weight_version: str | None
    model_weight_framework: str | None
    model_weight_license: str | None
    model_weight_usage_instructions: str | None
    dataset_source: str | None
    dataset_version: str | None
    dataset_format: str | None
    dataset_update_frequency: str | None
    protected_access_location: str | None
    last_confirmed_at: datetime | None
    review_due_at: datetime | None
    is_stale: bool
    can_update: bool
    can_manage_direction_links: bool
    directions: list[ResourceDirectionLinkResponse] = Field(default_factory=list)


class ResourceMaintenanceItemResponse(BaseModel):
    asset_id: str
    title: str
    asset_type: str
    last_confirmed_at: datetime | None
    review_due_at: datetime | None
    issue: Literal["review_missing", "review_overdue"]


class PublishAssetRequest(BaseModel):
    visibility_scope: Literal["lab_private", "lab_public"]
    description: str | None = Field(default=None, max_length=2000)
    publication_note: str | None = Field(default=None, max_length=2000)


class BulkPublishAssetRequest(BaseModel):
    asset_ids: list[str] = Field(min_length=1, max_length=100)
    visibility_scope: Literal["lab_private", "lab_public"]


class WithdrawAssetRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


class DeleteAssetRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


class LinkAssetToProjectRequest(BaseModel):
    project_id: str
    link_type: str = "reference"


class BulkLinkAssetsToProjectsRequest(BaseModel):
    asset_ids: list[str] = Field(min_length=1, max_length=100)
    project_ids: list[str] = Field(min_length=1, max_length=100)
    link_type: str = "reference"


class SaveGeneratedAssetRequest(BaseModel):
    project_id: str
    title: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1)
    asset_type: str = "generated_doc"
    metadata_json: dict = Field(default_factory=dict)


class AssetAccessRequestCreate(BaseModel):
    purpose: str = Field(min_length=1, max_length=2000)
    duration_days: int = Field(default=30, ge=1, le=365)
    project_id: str | None = None


class AssetAccessRequestReview(BaseModel):
    decision_note: str | None = Field(default=None, max_length=2000)


class DuplicateAccessRequestCreate(AssetAccessRequestCreate):
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class DuplicateAccessRequestResponse(BaseModel):
    id: str
    status: str


class TrainingMaterialGrantCreate(BaseModel):
    user_ids: list[str] = Field(min_length=1, max_length=100)
    duration_days: int = Field(default=90, ge=1, le=365)


class AssetAccessRequestResponse(BaseModel):
    id: str
    research_asset_id: str
    source_id: str | None = None
    asset_title: str | None = None
    requester_id: str
    requester_name: str | None = None
    project_id: str | None = None
    purpose: str
    duration_days: int
    status: str
    decided_by: str | None = None
    decided_by_name: str | None = None
    decision_note: str | None = None
    decided_at: datetime | None = None
    grant_valid_until: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LibrarySearchDirection(BaseModel):
    id: str
    name: str
    status: str


class LibraryCatalogSearchResult(BaseModel):
    id: str
    title: str
    asset_type: str
    description: str | None = None
    authors: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    directions: list[LibrarySearchDirection] = Field(default_factory=list)
    steward_name: str | None = None
    project_name: str | None = None
    date: str | None = None
    match_type: Literal["title", "keyword", "catalog", "semantic"] = "catalog"
    can_read_content: bool = False
    can_request_access: bool = False
    active_access_request_status: str | None = None


class LibraryFullTextSearchResult(LibraryCatalogSearchResult):
    snippet: str


class LibrarySearchResponse(BaseModel):
    full_text_results: list[LibraryFullTextSearchResult] = Field(default_factory=list)
    catalog_results: list[LibraryCatalogSearchResult] = Field(default_factory=list)
    full_text_search_available: bool = True
