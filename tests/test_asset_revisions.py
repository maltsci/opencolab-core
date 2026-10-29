import pytest
from pydantic import ValidationError
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base
from app.core.governance import AssetRevisionState
from app.models.asset_revision import (
    AssetContentMember,
    AssetRevision,
    AssetRevisionImmutableError,
)
from app.models.research_asset import ResearchAsset
from app.models.source import Source
from app.models.user import User
from app.schemas.asset_revision import AssetMemberCreate
from app.schemas.research_asset import ResearchAssetCatalogResponse
from app.services.asset_revision_service import (
    AssetRevisionLineageError,
    AssetRevisionSealedError,
    add_revision_member,
    create_revision,
    seal_revision,
)

pytestmark = pytest.mark.asyncio


async def test_asset_revision_tables_are_registered(db: AsyncSession) -> None:
    table_names = set(
        await db.run_sync(lambda session: inspect(session.bind).get_table_names())
    )

    assert "asset_revisions" in Base.metadata.tables
    assert "asset_content_members" in Base.metadata.tables
    assert "asset_revisions" in table_names
    assert "asset_content_members" in table_names


async def test_catalog_schema_excludes_protected_asset_fields(
    db: AsyncSession,
    admin_user: User,
) -> None:
    asset = ResearchAsset(
        asset_type="uploaded_file",
        asset_category="uploaded_material",
        title="Safe title",
        owner_id=admin_user.id,
        classification="confidential",
        catalog_metadata_json={"organism": "mouse"},
        protected_metadata_json={"storage_path": "/secure/project-x"},
        metadata_json={"legacy_secret": "hidden"},
        visibility_scope="private",
    )
    db.add(asset)
    await db.flush()

    response = ResearchAssetCatalogResponse.model_validate(asset)
    payload = response.model_dump()

    assert payload["asset_category"] == "uploaded_material"
    assert payload["catalog_metadata_json"] == {"organism": "mouse"}
    assert "source_id" not in payload
    assert "protected_metadata_json" not in payload
    assert "metadata_json" not in payload


async def test_revision_numbers_are_monotonic_and_seal_sets_current(
    db: AsyncSession,
    admin_user: User,
) -> None:
    source = Source(
        type="file",
        name="dataset.csv",
        owner_id=admin_user.id,
        processing_state="ready",
    )
    asset = ResearchAsset(
        asset_type="uploaded_file",
        asset_category="uploaded_material",
        title="Dataset",
        owner_id=admin_user.id,
    )
    db.add_all([source, asset])
    await db.flush()

    revision_one = await create_revision(
        db,
        asset=asset,
        created_by=admin_user.id,
        change_summary="Initial upload",
    )
    revision_two = await create_revision(
        db,
        asset=asset,
        created_by=admin_user.id,
        change_summary="Replacement upload",
    )
    await add_revision_member(
        db,
        revision=revision_one,
        member=AssetMemberCreate(
            role="primary",
            content_mode="managed",
            position=0,
            normalized_path="dataset.csv",
            display_name="dataset.csv",
            format="csv",
            managed_source_id=source.id,
        ),
    )

    await seal_revision(db, asset=asset, revision=revision_one)

    assert revision_one.revision_number == 1
    assert revision_two.revision_number == 2
    assert revision_one.processing_state == AssetRevisionState.READY
    assert revision_one.sealed_at is not None
    assert revision_one.manifest_sha256 is not None
    assert asset.current_revision_id == revision_one.id


async def test_member_modes_require_exactly_one_content_reference() -> None:
    with pytest.raises(ValidationError):
        AssetMemberCreate(
            role="primary",
            content_mode="managed",
            position=0,
            normalized_path="data.csv",
            display_name="data.csv",
            format="csv",
        )

    with pytest.raises(ValidationError):
        AssetMemberCreate(
            role="primary",
            content_mode="external",
            position=0,
            normalized_path="doi",
            display_name="DOI",
            format="doi",
            managed_source_id="source-id",
            external_reference_ciphertext="encrypted",
        )


async def test_sealed_revision_rejects_new_members(
    db: AsyncSession,
    admin_user: User,
) -> None:
    source = Source(type="file", name="data.txt", owner_id=admin_user.id)
    asset = ResearchAsset(
        asset_type="uploaded_file",
        asset_category="uploaded_material",
        title="Immutable asset",
        owner_id=admin_user.id,
    )
    db.add_all([source, asset])
    await db.flush()
    revision = await create_revision(
        db,
        asset=asset,
        created_by=admin_user.id,
        change_summary=None,
    )
    member = AssetMemberCreate(
        role="primary",
        content_mode="managed",
        position=0,
        normalized_path="data.txt",
        display_name="data.txt",
        format="txt",
        managed_source_id=source.id,
    )
    await add_revision_member(db, revision=revision, member=member)
    await seal_revision(db, asset=asset, revision=revision)

    with pytest.raises(AssetRevisionSealedError):
        await add_revision_member(
            db,
            revision=revision,
            member=member.model_copy(update={"position": 1, "normalized_path": "copy.txt"}),
        )


async def test_revision_cannot_be_sealed_for_another_asset(
    db: AsyncSession,
    admin_user: User,
) -> None:
    asset = ResearchAsset(asset_type="uploaded_file", title="Asset A")
    other_asset = ResearchAsset(asset_type="uploaded_file", title="Asset B")
    db.add_all([asset, other_asset])
    await db.flush()
    revision = await create_revision(
        db,
        asset=asset,
        created_by=admin_user.id,
        change_summary=None,
    )

    with pytest.raises(AssetRevisionLineageError):
        await seal_revision(db, asset=other_asset, revision=revision)


async def test_sealed_revision_member_cannot_be_updated(
    db: AsyncSession,
    admin_user: User,
) -> None:
    source = Source(type="file", name="locked.txt", owner_id=admin_user.id)
    asset = ResearchAsset(asset_type="uploaded_file", title="Locked asset")
    db.add_all([source, asset])
    await db.flush()
    revision = await create_revision(
        db,
        asset=asset,
        created_by=admin_user.id,
        change_summary=None,
    )
    member = await add_revision_member(
        db,
        revision=revision,
        member=AssetMemberCreate(
            role="primary",
            content_mode="managed",
            position=0,
            normalized_path="locked.txt",
            display_name="locked.txt",
            format="txt",
            managed_source_id=source.id,
        ),
    )
    await seal_revision(db, asset=asset, revision=revision)

    member.display_name = "changed.txt"
    with pytest.raises(AssetRevisionImmutableError):
        await db.flush()
    await db.rollback()


async def test_sealed_revision_member_cannot_be_deleted(
    db: AsyncSession,
    admin_user: User,
) -> None:
    source = Source(type="file", name="locked.txt", owner_id=admin_user.id)
    asset = ResearchAsset(asset_type="uploaded_file", title="Locked asset")
    db.add_all([source, asset])
    await db.flush()
    revision = await create_revision(
        db,
        asset=asset,
        created_by=admin_user.id,
        change_summary=None,
    )
    member = await add_revision_member(
        db,
        revision=revision,
        member=AssetMemberCreate(
            role="primary",
            content_mode="managed",
            position=0,
            normalized_path="locked.txt",
            display_name="locked.txt",
            format="txt",
            managed_source_id=source.id,
        ),
    )
    await seal_revision(db, asset=asset, revision=revision)

    await db.delete(member)
    with pytest.raises(AssetRevisionImmutableError):
        await db.flush()
    await db.rollback()


async def test_sealed_revision_rejects_direct_member_insert(
    db: AsyncSession,
    admin_user: User,
) -> None:
    source = Source(type="file", name="locked.txt", owner_id=admin_user.id)
    asset = ResearchAsset(asset_type="uploaded_file", title="Locked asset")
    db.add_all([source, asset])
    await db.flush()
    revision = await create_revision(
        db,
        asset=asset,
        created_by=admin_user.id,
        change_summary=None,
    )
    await add_revision_member(
        db,
        revision=revision,
        member=AssetMemberCreate(
            role="primary",
            content_mode="managed",
            position=0,
            normalized_path="locked.txt",
            display_name="locked.txt",
            format="txt",
            managed_source_id=source.id,
        ),
    )
    await seal_revision(db, asset=asset, revision=revision)

    db.add(
        AssetContentMember(
            asset_revision_id=revision.id,
            role="primary",
            content_mode="managed",
            position=1,
            normalized_path="copy.txt",
            display_name="copy.txt",
            format="txt",
            managed_source_id=source.id,
        )
    )
    with pytest.raises(AssetRevisionImmutableError):
        await db.flush()
    await db.rollback()


async def test_sealed_revision_cannot_be_updated(
    db: AsyncSession,
    admin_user: User,
) -> None:
    source = Source(type="file", name="locked.txt", owner_id=admin_user.id)
    asset = ResearchAsset(asset_type="uploaded_file", title="Locked asset")
    db.add_all([source, asset])
    await db.flush()
    revision = await create_revision(
        db,
        asset=asset,
        created_by=admin_user.id,
        change_summary=None,
    )
    await add_revision_member(
        db,
        revision=revision,
        member=AssetMemberCreate(
            role="primary",
            content_mode="managed",
            position=0,
            normalized_path="locked.txt",
            display_name="locked.txt",
            format="txt",
            managed_source_id=source.id,
        ),
    )
    await seal_revision(db, asset=asset, revision=revision)

    revision.change_summary = "Changed after sealing"
    with pytest.raises(AssetRevisionImmutableError):
        await db.flush()
    await db.rollback()
