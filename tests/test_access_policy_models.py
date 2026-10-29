from datetime import datetime, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base
from app.models.access_policy import AccessPolicy
from app.models.data_use_agreement import DataUseAgreement
from app.schemas.access_policy import AccessPolicyCreate, DataUseAgreementCreate


async def test_access_policy_and_agreement_tables_are_registered(
    db: AsyncSession,
) -> None:
    table_names = set(
        await db.run_sync(lambda session: inspect(session.bind).get_table_names())
    )

    assert "access_policies" in Base.metadata.tables
    assert "data_use_agreements" in Base.metadata.tables
    assert "access_policies" in table_names
    assert "data_use_agreements" in table_names


def test_access_policy_has_explicit_revision_and_condition_columns() -> None:
    columns = {column.name for column in AccessPolicy.__table__.columns}

    assert {
        "research_asset_id",
        "asset_revision_id",
        "applies_to_future_revisions",
        "subject_type",
        "subject_id",
        "group_role",
        "required_project_id",
        "required_agreement_id",
        "capabilities_json",
        "effect",
        "valid_from",
        "valid_until",
        "priority",
        "enabled",
    } <= columns
    assert "expression" not in columns
    assert "condition_json" not in columns


def test_revision_policy_cannot_also_apply_to_future_revisions() -> None:
    with pytest.raises(ValidationError):
        AccessPolicyCreate(
            research_asset_id="asset-id",
            asset_revision_id="revision-id",
            applies_to_future_revisions=True,
            subject_type="user",
            subject_id="user-id",
            capabilities_json=["content:preview"],
        )


def test_policy_schema_rejects_unknown_capability() -> None:
    with pytest.raises(ValidationError):
        AccessPolicyCreate(
            research_asset_id="asset-id",
            subject_type="user",
            subject_id="user-id",
            capabilities_json=["content:unknown"],
        )


def test_data_use_agreement_contains_reference_not_contract_text() -> None:
    columns = {column.name for column in DataUseAgreement.__table__.columns}

    assert {
        "name",
        "owning_group_id",
        "status",
        "valid_from",
        "valid_until",
        "allowed_project_id",
        "allowed_research_group_id",
        "allowed_capabilities_json",
        "reference",
        "created_by",
    } <= columns
    assert "contract_text" not in columns
    assert "content" not in columns


def test_data_use_agreement_requires_forward_time_range() -> None:
    now = datetime.now(timezone.utc)

    with pytest.raises(ValidationError):
        DataUseAgreementCreate(
            name="Invalid agreement",
            owning_group_id="group-id",
            status="active",
            valid_from=now,
            valid_until=now,
            allowed_capabilities_json=["content:download"],
            reference="DUA-2026-01",
        )
