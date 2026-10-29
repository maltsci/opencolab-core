from enum import StrEnum


class AssetClassification(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"
    TOP_SECRET = "top_secret"


class Capability(StrEnum):
    METADATA_VIEW = "metadata:view"
    CONTENT_PREVIEW = "content:preview"
    CONTENT_DOWNLOAD = "content:download"
    CONTENT_USE_IN_AGENT = "content:use_in_agent"
    ASSET_MANAGE = "asset:manage"


class AssetLifecycleStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class CatalogStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    WITHDRAWN = "withdrawn"


class GovernanceReviewStatus(StrEnum):
    PENDING = "pending"
    REVIEWED = "reviewed"


class AssetCategory(StrEnum):
    UPLOADED_MATERIAL = "uploaded_material"
    EXTERNAL_REFERENCE = "external_reference"
    GENERATED_DOCUMENT = "generated_document"
    RESEARCH_MEMORY = "research_memory"
    CONVERSATION_ARTIFACT = "conversation_artifact"
    EXPERIMENTAL_MATERIAL = "experimental_material"
    SCIENTIFIC_DATA = "scientific_data"


class AssetRevisionState(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class AssetMemberRole(StrEnum):
    PRIMARY = "primary"
    PACKAGE = "package"
    EXTRACTED = "extracted"
    INDEX = "index"
    ATTACHMENT = "attachment"


class AssetContentMode(StrEnum):
    MANAGED = "managed"
    EXTERNAL = "external"
    GENERATED = "generated"
