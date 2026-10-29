from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.governance import Capability
from app.models.asset_revision import AssetRevision
from app.models.research_asset import ResearchAsset
from app.models.user import User
from app.services.access_policy_service import AccessContext, authorize_asset


async def filter_authorized_asset_ids(
    db: AsyncSession,
    *,
    user: User,
    asset_ids: list[str],
    capability: Capability,
    project_id: str | None,
    purpose: str,
    actor_type: Literal["human", "agent"] = "human",
    agent_run_id: str | None = None,
) -> list[str]:
    """Return only candidate assets authorized at the time of this request."""
    if not asset_ids:
        return []

    assets = list(
        (
            await db.scalars(
                select(ResearchAsset).where(ResearchAsset.id.in_(asset_ids))
            )
        ).all()
    )
    assets_by_id = {asset.id: asset for asset in assets}
    allowed: list[str] = []

    for asset_id in asset_ids:
        asset = assets_by_id.get(asset_id)
        if asset is None:
            continue
        revision = (
            await db.get(AssetRevision, asset.current_revision_id)
            if asset.current_revision_id
            else None
        )
        decision = await authorize_asset(
            db=db,
            user=user,
            asset=asset,
            revision=revision,
            capability=capability,
            context=AccessContext(
                project_id=project_id,
                asset_revision_id=revision.id if revision else None,
                purpose=purpose,
                actor_type=actor_type,
                agent_run_id=agent_run_id,
            ),
        )
        if decision.allowed:
            allowed.append(asset_id)

    return allowed
