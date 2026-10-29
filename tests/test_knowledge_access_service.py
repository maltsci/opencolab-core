import pytest
import pytest_asyncio

from app.core.governance import Capability
from app.models.research_asset import ResearchAsset
from app.services.access_policy_service import PolicyDecision
from app.services.knowledge_access_service import filter_authorized_asset_ids

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def candidate_assets(db, admin_user) -> tuple[ResearchAsset, ResearchAsset]:
    visible = ResearchAsset(
        asset_type="paper",
        title="Visible candidate",
        owner_id=admin_user.id,
        visibility_scope="lab_public",
        classification="public",
        catalog_status="published",
        lifecycle_status="active",
    )
    hidden = ResearchAsset(
        asset_type="paper",
        title="Hidden candidate",
        owner_id=admin_user.id,
        visibility_scope="lab_private",
        classification="confidential",
        catalog_status="published",
        lifecycle_status="active",
    )
    db.add_all([visible, hidden])
    await db.flush()
    return visible, hidden


async def test_filter_authorized_asset_ids_rechecks_each_asset(
    db,
    researcher_user,
    candidate_assets,
    monkeypatch,
) -> None:
    visible, hidden = candidate_assets

    async def fake_authorize_asset(*, asset, capability, **kwargs):
        return PolicyDecision(
            allowed=asset.id == visible.id,
            capability=capability,
            reason_code="test_policy",
        )

    monkeypatch.setattr(
        "app.services.knowledge_access_service.authorize_asset",
        fake_authorize_asset,
    )

    result = await filter_authorized_asset_ids(
        db,
        user=researcher_user,
        asset_ids=[visible.id, hidden.id],
        capability=Capability.METADATA_VIEW,
        project_id=None,
        purpose="Knowledge entity discovery",
    )

    assert result == [visible.id]


async def test_revoked_grant_stops_authorizing_without_reindex(
    db,
    researcher_user,
    candidate_assets,
    monkeypatch,
) -> None:
    _, hidden = candidate_assets
    policy_state = {"enabled": True}

    async def fake_authorize_asset(*, capability, **kwargs):
        return PolicyDecision(
            allowed=policy_state["enabled"],
            capability=capability,
            reason_code="test_policy",
        )

    monkeypatch.setattr(
        "app.services.knowledge_access_service.authorize_asset",
        fake_authorize_asset,
    )

    before = await filter_authorized_asset_ids(
        db,
        user=researcher_user,
        asset_ids=[hidden.id],
        capability=Capability.CONTENT_USE_IN_AGENT,
        project_id=None,
        purpose="Lab knowledge question",
    )
    policy_state["enabled"] = False
    after = await filter_authorized_asset_ids(
        db,
        user=researcher_user,
        asset_ids=[hidden.id],
        capability=Capability.CONTENT_USE_IN_AGENT,
        project_id=None,
        purpose="Lab knowledge question",
    )

    assert before == [hidden.id]
    assert after == []
