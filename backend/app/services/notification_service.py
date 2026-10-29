from datetime import UTC, datetime

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ROLE_ADMIN
from app.core.governance import Capability
from app.models.access_policy import AccessPolicy
from app.models.access_request import AccessRequest
from app.models.notification import Notification
from app.models.project import ResearcherProject
from app.models.research_asset import ResearchAsset
from app.models.user import User
from app.services.research_asset_service import can_user_manage_asset


async def can_review_access_request(db: AsyncSession, user: User, asset: ResearchAsset) -> bool:
    if await can_user_manage_asset(db, user, asset) or user.id == asset.owner_id:
        return True
    if asset.origin_project_id is None:
        return False
    return await db.scalar(select(ResearcherProject.id).where(
        ResearcherProject.project_id == asset.origin_project_id,
        ResearcherProject.researcher_id == user.id,
        ResearcherProject.role == "owner",
    )) is not None


async def notify_access_request(db: AsyncSession, request: AccessRequest, asset: ResearchAsset) -> None:
    owner_ids = {asset.owner_id, asset.steward_user_id}
    if asset.origin_project_id:
        owner_ids.update((await db.scalars(select(ResearcherProject.researcher_id).where(
            ResearcherProject.project_id == asset.origin_project_id,
            ResearcherProject.role == "owner",
        ))).all())
    query = select(User).where(User.archived_at.is_(None))
    policies = (await db.scalars(select(AccessPolicy).where(
        AccessPolicy.research_asset_id == asset.id, AccessPolicy.enabled.is_(True),
        AccessPolicy.effect == "allow",
    ))).all()
    # Custom management policies can address groups or roles as well as users.
    if not any(Capability.ASSET_MANAGE in (policy.capabilities_json or []) for policy in policies):
        query = query.where(or_(User.role == ROLE_ADMIN, User.id.in_(owner_ids - {None})))
    for reviewer in (await db.scalars(query)).all():
        if reviewer.id != request.requester_id and await can_review_access_request(db, reviewer, asset):
            db.add(Notification(
                user_id=reviewer.id, kind="access_request_pending", access_request_id=request.id,
            ))


async def notify_access_decision(db: AsyncSession, request: AccessRequest) -> None:
    await db.execute(update(Notification).where(
        Notification.access_request_id == request.id,
        Notification.kind == "access_request_pending",
        Notification.read_at.is_(None),
    ).values(read_at=datetime.now(UTC)))
    if request.status in {"approved", "rejected"}:
        db.add(Notification(
            user_id=request.requester_id, kind=f"access_request_{request.status}",
            access_request_id=request.id,
        ))
