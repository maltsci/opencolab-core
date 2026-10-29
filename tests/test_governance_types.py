from app.core.governance import (
    AssetCategory,
    AssetClassification,
    AssetContentMode,
    AssetLifecycleStatus,
    AssetMemberRole,
    AssetRevisionState,
    Capability,
    CatalogStatus,
    GovernanceReviewStatus,
)


def test_governance_values_are_stable_api_strings() -> None:
    assert AssetClassification.PUBLIC == "public"
    assert AssetClassification.INTERNAL == "internal"
    assert AssetClassification.CONFIDENTIAL == "confidential"
    assert AssetClassification.RESTRICTED == "restricted"
    assert AssetClassification.TOP_SECRET == "top_secret"
    assert Capability.METADATA_VIEW == "metadata:view"
    assert Capability.CONTENT_PREVIEW == "content:preview"
    assert Capability.CONTENT_DOWNLOAD == "content:download"
    assert Capability.CONTENT_USE_IN_AGENT == "content:use_in_agent"
    assert Capability.ASSET_MANAGE == "asset:manage"
    assert AssetLifecycleStatus.ACTIVE == "active"
    assert AssetLifecycleStatus.ARCHIVED == "archived"
    assert CatalogStatus.DRAFT == "draft"
    assert CatalogStatus.PUBLISHED == "published"
    assert CatalogStatus.WITHDRAWN == "withdrawn"
    assert GovernanceReviewStatus.PENDING == "pending"
    assert GovernanceReviewStatus.REVIEWED == "reviewed"


def test_research_asset_taxonomy_values_are_stable_api_strings() -> None:
    assert AssetCategory.UPLOADED_MATERIAL == "uploaded_material"
    assert AssetCategory.EXTERNAL_REFERENCE == "external_reference"
    assert AssetCategory.GENERATED_DOCUMENT == "generated_document"
    assert AssetCategory.RESEARCH_MEMORY == "research_memory"
    assert AssetCategory.CONVERSATION_ARTIFACT == "conversation_artifact"
    assert AssetCategory.EXPERIMENTAL_MATERIAL == "experimental_material"
    assert AssetCategory.SCIENTIFIC_DATA == "scientific_data"
    assert AssetRevisionState.PENDING == "pending"
    assert AssetRevisionState.PROCESSING == "processing"
    assert AssetRevisionState.READY == "ready"
    assert AssetRevisionState.FAILED == "failed"
    assert AssetMemberRole.PRIMARY == "primary"
    assert AssetMemberRole.PACKAGE == "package"
    assert AssetMemberRole.EXTRACTED == "extracted"
    assert AssetMemberRole.INDEX == "index"
    assert AssetMemberRole.ATTACHMENT == "attachment"
    assert AssetContentMode.MANAGED == "managed"
    assert AssetContentMode.EXTERNAL == "external"
    assert AssetContentMode.GENERATED == "generated"
