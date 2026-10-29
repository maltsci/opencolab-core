from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base
from app.models.data_asset import DataAsset
from app.schemas.data_asset import DataAssetResponse


async def test_data_asset_table_is_registered(db: AsyncSession) -> None:
    table_names = set(
        await db.run_sync(lambda session: inspect(session.bind).get_table_names())
    )

    assert "data_assets" in Base.metadata.tables
    assert "data_assets" in table_names


def test_data_asset_contains_scientific_semantics_without_storage_identity() -> None:
    columns = {column.name for column in DataAsset.__table__.columns}
    schema_fields = set(DataAssetResponse.model_fields)

    assert {
        "research_asset_id",
        "research_object_id",
        "data_type",
        "data_modality",
        "scientific_metadata_json",
    } <= columns
    assert "managed_source_id" not in columns
    assert "storage_mode" not in columns
    assert "external_locator_ciphertext" not in columns
    assert "managed_source_id" not in schema_fields
    assert "storage_mode" not in schema_fields
    assert "external_locator_ciphertext" not in schema_fields
