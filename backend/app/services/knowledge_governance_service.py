from datetime import datetime, timezone

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ROLE_ADMIN, ROLE_PI
from app.models.knowledge_governance import (
    KnowledgeChangeEvent,
    KnowledgeSuggestion,
    ResearchDirectionSteward,
    ResearchGroupSteward,
)
from app.models.member_profile import MemberProfile
from app.models.research_asset import ResearchAsset
from app.models.research_direction import ResearchDirection, ResearchDirectionRelation
from app.models.research_direction_link import ResearchObjectDirection
from app.models.research_group import ResearchGroup, ResearchGroupMember
from app.models.research_object import ResearchObject
from app.models.user import User
from app.schemas.knowledge_governance import (
    KnowledgeHealthResponse,
    KnowledgeInboxResponse,
    KnowledgeSuggestionAuditResponse,
)
from app.services.research_group_service import (
    can_manage_research_group,
    get_research_group,
    is_active_group_member,
)


class KnowledgeGovernanceNotFoundError(LookupError):
    pass


class KnowledgeGovernancePermissionError(PermissionError):
    pass


class KnowledgeGovernanceConflictError(ValueError):
    pass


class KnowledgeGovernanceValidationError(ValueError):
    pass


def _resource_review_due_at(asset: ResearchAsset) -> datetime | None:
    metadata = asset.catalog_metadata_json
    profile = metadata.get("resource_profile") if isinstance(metadata, dict) else None
    value = profile.get("review_due_at") if isinstance(profile, dict) else None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


async def _require_group_manager(
    db: AsyncSession,
    *,
    actor: User,
    group_id: str,
) -> ResearchGroup:
    group = await get_research_group(db, group_id=group_id)
    if not await can_manage_research_group(db, actor=actor, group_id=group_id):
        raise KnowledgeGovernancePermissionError("Research group stewardship denied")
    return group


async def _get_direction(
    db: AsyncSession,
    *,
    direction_id: str,
) -> ResearchDirection:
    direction = await db.get(ResearchDirection, direction_id)
    if direction is None:
        raise KnowledgeGovernanceNotFoundError("Research direction not found")
    return direction


async def _require_active_direction(
    db: AsyncSession,
    *,
    direction_id: str,
) -> ResearchDirection:
    direction = await _get_direction(db, direction_id=direction_id)
    if direction.status != "active":
        raise KnowledgeGovernanceConflictError(
            "Only active research directions can have stewards"
        )
    return direction


async def _require_direction_manager(
    db: AsyncSession,
    *,
    actor: User,
    direction_id: str,
) -> ResearchDirection:
    direction = await _require_active_direction(db, direction_id=direction_id)
    if actor.role not in (ROLE_ADMIN, ROLE_PI):
        raise KnowledgeGovernancePermissionError(
            "Research direction stewardship denied"
        )
    return direction


async def is_group_steward(
    db: AsyncSession,
    *,
    group_id: str,
    user_id: str,
) -> bool:
    stmt = (
        select(ResearchGroupSteward.id)
        .join(ResearchGroup, ResearchGroup.id == ResearchGroupSteward.group_id)
        .join(
            ResearchGroupMember,
            (ResearchGroupMember.group_id == ResearchGroupSteward.group_id)
            & (ResearchGroupMember.user_id == ResearchGroupSteward.user_id),
        )
        .where(
            ResearchGroupSteward.group_id == group_id,
            ResearchGroupSteward.user_id == user_id,
            ResearchGroupSteward.revoked_at.is_(None),
            ResearchGroup.archived_at.is_(None),
            ResearchGroupMember.removed_at.is_(None),
        )
    )
    return (await db.scalar(stmt)) is not None


async def is_direction_steward(
    db: AsyncSession,
    *,
    direction_id: str,
    user_id: str,
) -> bool:
    stmt = (
        select(ResearchDirectionSteward.id)
        .join(
            ResearchDirection,
            ResearchDirection.id == ResearchDirectionSteward.direction_id,
        )
        .where(
            ResearchDirectionSteward.direction_id == direction_id,
            ResearchDirectionSteward.user_id == user_id,
            ResearchDirectionSteward.revoked_at.is_(None),
            ResearchDirection.status == "active",
        )
    )
    return (await db.scalar(stmt)) is not None


async def can_review_knowledge_suggestions(
    db: AsyncSession,
    *,
    actor: User,
) -> bool:
    if actor.role in (ROLE_ADMIN, ROLE_PI):
        return True

    direction_stewardship = (
        select(ResearchDirectionSteward.id)
        .join(
            ResearchDirection,
            ResearchDirection.id == ResearchDirectionSteward.direction_id,
        )
        .where(
            ResearchDirectionSteward.user_id == actor.id,
            ResearchDirectionSteward.revoked_at.is_(None),
            ResearchDirection.status == "active",
        )
    )
    if (await db.scalar(direction_stewardship)) is not None:
        return True

    group_stewardship = (
        select(ResearchGroupSteward.id)
        .join(ResearchGroup, ResearchGroup.id == ResearchGroupSteward.group_id)
        .join(
            ResearchGroupMember,
            (ResearchGroupMember.group_id == ResearchGroupSteward.group_id)
            & (ResearchGroupMember.user_id == ResearchGroupSteward.user_id),
        )
        .where(
            ResearchGroupSteward.user_id == actor.id,
            ResearchGroupSteward.revoked_at.is_(None),
            ResearchGroup.archived_at.is_(None),
            ResearchGroupMember.removed_at.is_(None),
        )
    )
    return (await db.scalar(group_stewardship)) is not None


async def can_govern_direction(
    db: AsyncSession,
    *,
    actor: User,
    direction_id: str,
) -> bool:
    if actor.role in (ROLE_ADMIN, ROLE_PI):
        return True
    return await is_direction_steward(
        db,
        direction_id=direction_id,
        user_id=actor.id,
    )


async def can_govern_member_direction(
    db: AsyncSession,
    *,
    actor: User,
    user_id: str,
    direction_id: str,
) -> bool:
    if await can_govern_direction(db, actor=actor, direction_id=direction_id):
        return True
    stmt = (
        select(ResearchGroupSteward.id)
        .join(ResearchGroup, ResearchGroup.id == ResearchGroupSteward.group_id)
        .join(
            ResearchGroupMember,
            ResearchGroupMember.group_id == ResearchGroupSteward.group_id,
        )
        .where(
            ResearchGroupSteward.user_id == actor.id,
            ResearchGroupSteward.revoked_at.is_(None),
            ResearchGroup.archived_at.is_(None),
            ResearchGroupMember.user_id == user_id,
            ResearchGroupMember.removed_at.is_(None),
        )
    )
    return (await db.scalar(stmt)) is not None


async def can_govern_asset_direction(
    db: AsyncSession,
    *,
    actor: User,
    asset_id: str,
    direction_id: str,
) -> bool:
    if await can_govern_direction(db, actor=actor, direction_id=direction_id):
        return True
    asset = await db.get(ResearchAsset, asset_id)
    if asset is None or asset.owning_group_id is None:
        return False
    return await is_group_steward(
        db,
        group_id=asset.owning_group_id,
        user_id=actor.id,
    )


async def assign_group_steward(
    db: AsyncSession,
    *,
    actor: User,
    group_id: str,
    user_id: str,
) -> ResearchGroupSteward:
    await _require_group_manager(db, actor=actor, group_id=group_id)
    active_member = await is_active_group_member(
        db,
        group_id=group_id,
        user_id=user_id,
    )
    if not active_member:
        raise KnowledgeGovernanceConflictError(
            "Group steward must be an active group member"
        )
    assignment = await db.scalar(
        select(ResearchGroupSteward).where(
            ResearchGroupSteward.group_id == group_id,
            ResearchGroupSteward.user_id == user_id,
        )
    )
    if assignment is None:
        assignment = ResearchGroupSteward(
            group_id=group_id,
            user_id=user_id,
            created_by=actor.id,
        )
        db.add(assignment)
    elif assignment.revoked_at is None:
        raise KnowledgeGovernanceConflictError("Group steward already assigned")
    else:
        assignment.revoked_at = None
        assignment.created_by = actor.id
    await db.flush()
    return assignment


async def revoke_group_steward(
    db: AsyncSession,
    *,
    actor: User,
    group_id: str,
    user_id: str,
) -> None:
    await _require_group_manager(db, actor=actor, group_id=group_id)
    assignment = await db.scalar(
        select(ResearchGroupSteward).where(
            ResearchGroupSteward.group_id == group_id,
            ResearchGroupSteward.user_id == user_id,
            ResearchGroupSteward.revoked_at.is_(None),
        )
    )
    if assignment is None:
        raise KnowledgeGovernanceNotFoundError("Active group steward not found")
    assignment.revoked_at = datetime.now(timezone.utc)
    await db.flush()


async def list_group_stewards(
    db: AsyncSession,
    *,
    actor: User,
    group_id: str,
) -> list[ResearchGroupSteward]:
    await _require_group_manager(db, actor=actor, group_id=group_id)
    stmt = (
        select(ResearchGroupSteward)
        .where(
            ResearchGroupSteward.group_id == group_id,
            ResearchGroupSteward.revoked_at.is_(None),
        )
        .order_by(ResearchGroupSteward.created_at, ResearchGroupSteward.id)
    )
    return list((await db.scalars(stmt)).all())


async def assign_direction_steward(
    db: AsyncSession,
    *,
    actor: User,
    direction_id: str,
    user_id: str,
) -> ResearchDirectionSteward:
    await _require_direction_manager(
        db,
        actor=actor,
        direction_id=direction_id,
    )
    if await db.get(User, user_id) is None:
        raise KnowledgeGovernanceNotFoundError("User not found")
    assignment = await db.scalar(
        select(ResearchDirectionSteward).where(
            ResearchDirectionSteward.direction_id == direction_id,
            ResearchDirectionSteward.user_id == user_id,
        )
    )
    if assignment is None:
        assignment = ResearchDirectionSteward(
            direction_id=direction_id,
            user_id=user_id,
            created_by=actor.id,
        )
        db.add(assignment)
    elif assignment.revoked_at is None:
        raise KnowledgeGovernanceConflictError("Direction steward already assigned")
    else:
        assignment.revoked_at = None
        assignment.created_by = actor.id
    await db.flush()
    return assignment


async def revoke_direction_steward(
    db: AsyncSession,
    *,
    actor: User,
    direction_id: str,
    user_id: str,
) -> None:
    await _require_direction_manager(
        db,
        actor=actor,
        direction_id=direction_id,
    )
    assignment = await db.scalar(
        select(ResearchDirectionSteward).where(
            ResearchDirectionSteward.direction_id == direction_id,
            ResearchDirectionSteward.user_id == user_id,
            ResearchDirectionSteward.revoked_at.is_(None),
        )
    )
    if assignment is None:
        raise KnowledgeGovernanceNotFoundError("Active direction steward not found")
    assignment.revoked_at = datetime.now(timezone.utc)
    await db.flush()


async def list_direction_stewards(
    db: AsyncSession,
    *,
    actor: User,
    direction_id: str,
) -> list[ResearchDirectionSteward]:
    await _require_direction_manager(
        db,
        actor=actor,
        direction_id=direction_id,
    )
    stmt = (
        select(ResearchDirectionSteward)
        .where(
            ResearchDirectionSteward.direction_id == direction_id,
            ResearchDirectionSteward.revoked_at.is_(None),
        )
        .order_by(ResearchDirectionSteward.created_at, ResearchDirectionSteward.id)
    )
    return list((await db.scalars(stmt)).all())


_RESTRICTED_JSON_KEYS = {
    "content",
    "content_json",
    "raw_content",
    "text",
    "body",
    "chunk",
    "chunks",
    "prompt",
    "response",
    "document",
}


def _validate_safe_json(value: object) -> None:
    if isinstance(value, dict):
        for key, nested_value in value.items():
            if not isinstance(key, str):
                raise KnowledgeGovernanceValidationError(
                    "Suggestion JSON keys must be strings"
                )
            if key.casefold() in _RESTRICTED_JSON_KEYS:
                raise KnowledgeGovernanceValidationError(
                    "Suggestion payload may not contain restricted content"
                )
            _validate_safe_json(nested_value)
    elif isinstance(value, list):
        for item in value:
            _validate_safe_json(item)
    elif not isinstance(value, (str, int, float, bool, type(None))):
        raise KnowledgeGovernanceValidationError("Suggestion JSON must be serializable")


def _require_exact_payload_keys(payload: dict, expected_keys: set[str]) -> None:
    if set(payload) != expected_keys:
        raise KnowledgeGovernanceValidationError("Invalid suggestion payload")


async def submit_knowledge_suggestion(
    db: AsyncSession,
    *,
    actor: User,
    target_type: str,
    target_id: str | None,
    action: str,
    payload_json: dict,
    evidence_json: dict,
) -> KnowledgeSuggestion:
    _validate_safe_json(payload_json)
    _validate_safe_json(evidence_json)
    suggestion = KnowledgeSuggestion(
        target_type=target_type,
        target_id=target_id,
        action=action,
        payload_json=payload_json,
        evidence_json=evidence_json,
        submitted_by=actor.id,
        submitted_by_type="human",
    )
    db.add(suggestion)
    await db.flush()
    return suggestion


async def _can_review_suggestion(
    db: AsyncSession,
    *,
    actor: User,
    suggestion: KnowledgeSuggestion,
) -> bool:
    payload = suggestion.payload_json
    if suggestion.target_type == "research_object_direction_link":
        direction_id = payload.get("direction_id")
        return isinstance(direction_id, str) and await can_govern_direction(
            db, actor=actor, direction_id=direction_id
        )
    if suggestion.target_type == "research_direction_relation":
        source_direction_id = payload.get("source_direction_id")
        return isinstance(source_direction_id, str) and await can_govern_direction(
            db, actor=actor, direction_id=source_direction_id
        )
    if suggestion.target_type == "member_direction_link":
        user_id = payload.get("user_id")
        direction_id = payload.get("direction_id")
        return (
            isinstance(user_id, str)
            and isinstance(direction_id, str)
            and await can_govern_member_direction(
                db,
                actor=actor,
                user_id=user_id,
                direction_id=direction_id,
            )
        )
    if suggestion.target_type == "resource_direction_link":
        asset_id = payload.get("research_asset_id")
        direction_id = payload.get("direction_id")
        return (
            isinstance(asset_id, str)
            and isinstance(direction_id, str)
            and await can_govern_asset_direction(
                db,
                actor=actor,
                asset_id=asset_id,
                direction_id=direction_id,
            )
        )
    if suggestion.target_type == "project_direction_link":
        direction_id = payload.get("direction_id")
        return isinstance(direction_id, str) and await can_govern_direction(
            db, actor=actor, direction_id=direction_id
        )
    if suggestion.target_type == "research_direction":
        if suggestion.action == "create":
            return actor.role in (ROLE_ADMIN, ROLE_PI)
        direction_id = suggestion.target_id or payload.get("direction_id")
        return isinstance(direction_id, str) and await can_govern_direction(
            db, actor=actor, direction_id=direction_id
        )
    return False


async def _get_suggestion_for_decision(
    db: AsyncSession,
    *,
    suggestion_id: str,
) -> KnowledgeSuggestion:
    suggestion = await db.scalar(
        select(KnowledgeSuggestion)
        .where(KnowledgeSuggestion.id == suggestion_id)
        .with_for_update()
    )
    if suggestion is None:
        raise KnowledgeGovernanceNotFoundError("Knowledge suggestion not found")
    return suggestion


async def get_knowledge_suggestion(
    db: AsyncSession,
    *,
    actor: User,
    suggestion_id: str,
) -> KnowledgeSuggestion:
    suggestion = await db.get(KnowledgeSuggestion, suggestion_id)
    if suggestion is None:
        raise KnowledgeGovernanceNotFoundError("Knowledge suggestion not found")
    if suggestion.submitted_by == actor.id or await _can_review_suggestion(
        db, actor=actor, suggestion=suggestion
    ):
        return suggestion
    raise KnowledgeGovernancePermissionError("Knowledge suggestion access denied")


async def get_knowledge_suggestion_audit(
    db: AsyncSession,
    *,
    actor: User,
    suggestion_id: str,
) -> KnowledgeSuggestionAuditResponse | None:
    await get_knowledge_suggestion(db, actor=actor, suggestion_id=suggestion_id)
    event = await db.scalar(
        select(KnowledgeChangeEvent)
        .where(KnowledgeChangeEvent.suggestion_id == suggestion_id)
        .order_by(KnowledgeChangeEvent.created_at.desc(), KnowledgeChangeEvent.id.desc())
        .limit(1)
    )
    if event is None:
        return None
    return KnowledgeSuggestionAuditResponse.model_validate(event)


async def list_knowledge_suggestions(
    db: AsyncSession,
    *,
    actor: User,
    suggestion_status: str | None,
    limit: int,
    before_id: str | None,
    reviewable_only: bool = False,
) -> list[KnowledgeSuggestion]:
    if suggestion_status not in {None, "pending", "approved", "rejected"}:
        raise KnowledgeGovernanceValidationError("Invalid suggestion status")
    stmt = select(KnowledgeSuggestion)
    if suggestion_status is not None:
        stmt = stmt.where(KnowledgeSuggestion.status == suggestion_status)
    if before_id is not None:
        anchor = await db.get(KnowledgeSuggestion, before_id)
        if anchor is not None:
            stmt = stmt.where(
                or_(
                    KnowledgeSuggestion.created_at < anchor.created_at,
                    and_(
                        KnowledgeSuggestion.created_at == anchor.created_at,
                        KnowledgeSuggestion.id < anchor.id,
                    ),
                )
            )
    candidates = list(
        (
            await db.scalars(
                stmt.order_by(
                    KnowledgeSuggestion.created_at.desc(), KnowledgeSuggestion.id.desc()
                ).limit(limit * 4)
            )
        ).all()
    )
    visible: list[KnowledgeSuggestion] = []
    for suggestion in candidates:
        can_review = await _can_review_suggestion(
            db, actor=actor, suggestion=suggestion
        )
        if can_review or (not reviewable_only and suggestion.submitted_by == actor.id):
            visible.append(suggestion)
            if len(visible) == limit:
                break
    return visible


async def get_knowledge_inbox(
    db: AsyncSession,
    *,
    actor: User,
    limit: int,
) -> KnowledgeInboxResponse:
    review_items = await list_knowledge_suggestions(
        db,
        actor=actor,
        suggestion_status="pending",
        limit=limit,
        before_id=None,
        reviewable_only=True,
    )
    decision_items = list(
        (
            await db.scalars(
                select(KnowledgeSuggestion)
                .where(
                    KnowledgeSuggestion.submitted_by == actor.id,
                    KnowledgeSuggestion.status.in_(("approved", "rejected")),
                )
                .order_by(
                    KnowledgeSuggestion.decided_at.desc(),
                    KnowledgeSuggestion.id.desc(),
                )
                .limit(limit)
            )
        ).all()
    )
    unread_decision_count = await db.scalar(
        select(func.count())
        .select_from(KnowledgeSuggestion)
        .where(
            KnowledgeSuggestion.submitted_by == actor.id,
            KnowledgeSuggestion.status.in_(("approved", "rejected")),
            KnowledgeSuggestion.decision_seen_at.is_(None),
        )
    )
    return KnowledgeInboxResponse(
        review_items=review_items,
        decision_items=decision_items,
        unread_decision_count=unread_decision_count or 0,
    )


async def get_knowledge_health(db: AsyncSession) -> KnowledgeHealthResponse:
    now = datetime.now(timezone.utc)
    member_profile_review_count = await db.scalar(
        select(func.count())
        .select_from(User)
        .outerjoin(MemberProfile, MemberProfile.user_id == User.id)
        .where(
            User.archived_at.is_(None),
            or_(
                MemberProfile.id.is_(None),
                MemberProfile.review_due_at.is_(None),
                MemberProfile.review_due_at < now,
            )
        )
    )
    direction_review_count = await db.scalar(
        select(func.count())
        .select_from(ResearchDirection)
        .where(
            ResearchDirection.status == "active",
            or_(
                ResearchDirection.review_due_at.is_(None),
                ResearchDirection.review_due_at < now,
            ),
        )
    )
    assets = list(
        (
            await db.scalars(
                select(ResearchAsset).where(
                    ResearchAsset.publication_status == "active",
                    ResearchAsset.deleted_at.is_(None),
                )
            )
        ).all()
    )
    resource_review_count = sum(
        review_due_at is None or review_due_at < now
        for review_due_at in (_resource_review_due_at(asset) for asset in assets)
    )
    pending_suggestion_count = await db.scalar(
        select(func.count())
        .select_from(KnowledgeSuggestion)
        .where(KnowledgeSuggestion.status == "pending")
    )
    return KnowledgeHealthResponse(
        member_profile_review_count=member_profile_review_count or 0,
        direction_review_count=direction_review_count or 0,
        resource_review_count=resource_review_count,
        pending_suggestion_count=pending_suggestion_count or 0,
    )


async def mark_knowledge_inbox_decisions_seen(
    db: AsyncSession,
    *,
    actor: User,
) -> int:
    result = await db.execute(
        update(KnowledgeSuggestion)
        .where(
            KnowledgeSuggestion.submitted_by == actor.id,
            KnowledgeSuggestion.status.in_(("approved", "rejected")),
            KnowledgeSuggestion.decision_seen_at.is_(None),
        )
        .values(decision_seen_at=datetime.now(timezone.utc))
    )
    return result.rowcount or 0


async def _apply_research_object_direction_suggestion(
    db: AsyncSession,
    *,
    actor: User,
    suggestion: KnowledgeSuggestion,
) -> tuple[str, str, dict, dict]:
    payload = suggestion.payload_json
    _require_exact_payload_keys(
        payload,
        {"research_object_id", "direction_id", "relation_type", "reason"},
    )
    research_object_id = payload["research_object_id"]
    direction_id = payload["direction_id"]
    relation_type = payload["relation_type"]
    reason = payload["reason"]
    if not all(
        isinstance(value, str)
        for value in (research_object_id, direction_id, relation_type, reason)
    ):
        raise KnowledgeGovernanceValidationError("Invalid suggestion payload")
    if relation_type not in {"belongs_to", "informs"} or not reason.strip():
        raise KnowledgeGovernanceValidationError("Invalid suggestion payload")
    if await db.get(ResearchObject, research_object_id) is None:
        raise KnowledgeGovernanceNotFoundError("Research object not found")
    await _require_active_direction(db, direction_id=direction_id)
    relation = ResearchObjectDirection(
        research_object_id=research_object_id,
        direction_id=direction_id,
        relation_type=relation_type,
        reason=reason.strip(),
        created_by=actor.id,
    )
    db.add(relation)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise KnowledgeGovernanceConflictError(
            "Research object direction relation already exists"
        ) from exc
    after_json = {
        "research_object_id": relation.research_object_id,
        "direction_id": relation.direction_id,
        "relation_type": relation.relation_type,
        "reason": relation.reason,
    }
    return "research_object_direction_link", relation.id, {}, after_json


async def _apply_research_direction_relation_suggestion(
    db: AsyncSession,
    *,
    actor: User,
    suggestion: KnowledgeSuggestion,
) -> tuple[str, str, dict, dict]:
    payload = suggestion.payload_json
    _require_exact_payload_keys(
        payload,
        {"source_direction_id", "target_direction_id", "reason", "evidence_json"},
    )
    source_direction_id = payload["source_direction_id"]
    target_direction_id = payload["target_direction_id"]
    reason = payload["reason"]
    evidence_json = payload["evidence_json"]
    if not (
        isinstance(source_direction_id, str)
        and isinstance(target_direction_id, str)
        and isinstance(reason, str)
        and isinstance(evidence_json, dict)
        and reason.strip()
    ):
        raise KnowledgeGovernanceValidationError("Invalid suggestion payload")
    _validate_safe_json(evidence_json)
    if source_direction_id == target_direction_id:
        raise KnowledgeGovernanceConflictError(
            "A research direction cannot be related to itself"
        )
    source = await _require_active_direction(db, direction_id=source_direction_id)
    target = await _require_active_direction(db, direction_id=target_direction_id)
    direction_a_id, direction_b_id = sorted((source.id, target.id))
    relation = ResearchDirectionRelation(
        direction_a_id=direction_a_id,
        direction_b_id=direction_b_id,
        relation_type="related",
        reason=reason.strip(),
        evidence_json=evidence_json,
        created_by=actor.id,
    )
    db.add(relation)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise KnowledgeGovernanceConflictError(
            "Research direction relation already exists"
        ) from exc
    after_json = {
        "direction_a_id": relation.direction_a_id,
        "direction_b_id": relation.direction_b_id,
        "relation_type": relation.relation_type,
        "reason": relation.reason,
        "evidence_json": relation.evidence_json,
    }
    return "research_direction_relation", relation.id, {}, after_json


async def _apply_research_direction_create_suggestion(
    db: AsyncSession,
    *,
    actor: User,
    suggestion: KnowledgeSuggestion,
) -> tuple[str, str, dict, dict]:
    payload = suggestion.payload_json
    _require_exact_payload_keys(payload, {"research_object_id", "name", "reason"})
    research_object_id = payload["research_object_id"]
    name = payload["name"]
    reason = payload["reason"]
    if not all(isinstance(value, str) for value in (research_object_id, name, reason)):
        raise KnowledgeGovernanceValidationError("Invalid suggestion payload")

    display_name = " ".join(name.split())
    normalized_name = display_name.casefold()
    normalized_reason = reason.strip()
    if not display_name or not normalized_reason:
        raise KnowledgeGovernanceValidationError("Invalid suggestion payload")
    if await db.get(ResearchObject, research_object_id) is None:
        raise KnowledgeGovernanceNotFoundError("Research object not found")
    existing_direction = await db.scalar(
        select(ResearchDirection.id).where(
            ResearchDirection.normalized_name == normalized_name,
            ResearchDirection.status == "active",
        )
    )
    if existing_direction is not None:
        raise KnowledgeGovernanceConflictError("Research direction name already exists")

    direction = ResearchDirection(
        name=display_name,
        normalized_name=normalized_name,
        created_by=actor.id,
    )
    db.add(direction)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise KnowledgeGovernanceConflictError(
            "Research direction name already exists"
        ) from exc

    relation = ResearchObjectDirection(
        research_object_id=research_object_id,
        direction_id=direction.id,
        relation_type="belongs_to",
        reason=normalized_reason,
        created_by=actor.id,
    )
    db.add(relation)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise KnowledgeGovernanceConflictError(
            "Research direction creation suggestion cannot be applied"
        ) from exc
    after_json = {
        "direction_id": direction.id,
        "name": direction.name,
        "research_object_id": relation.research_object_id,
        "relation_type": relation.relation_type,
        "reason": relation.reason,
    }
    return "research_direction", direction.id, {}, after_json


async def decide_knowledge_suggestion(
    db: AsyncSession,
    *,
    actor: User,
    suggestion_id: str,
    decision: str,
    reason: str,
) -> KnowledgeSuggestion:
    suggestion = await _get_suggestion_for_decision(db, suggestion_id=suggestion_id)
    if suggestion.status != "pending":
        raise KnowledgeGovernanceConflictError("Knowledge suggestion already decided")
    if not await _can_review_suggestion(db, actor=actor, suggestion=suggestion):
        raise KnowledgeGovernancePermissionError("Knowledge suggestion review denied")

    normalized_reason = reason.strip()
    if not normalized_reason:
        raise KnowledgeGovernanceValidationError("Decision reason is required")
    if decision == "approved":
        if suggestion.target_type == "research_object_direction_link":
            entity_type, entity_id, before_json, after_json = (
                await _apply_research_object_direction_suggestion(
                    db, actor=actor, suggestion=suggestion
                )
            )
        elif suggestion.target_type == "research_direction_relation":
            entity_type, entity_id, before_json, after_json = (
                await _apply_research_direction_relation_suggestion(
                    db, actor=actor, suggestion=suggestion
                )
            )
        elif (
            suggestion.target_type == "research_direction"
            and suggestion.action == "create"
        ):
            entity_type, entity_id, before_json, after_json = (
                await _apply_research_direction_create_suggestion(
                    db, actor=actor, suggestion=suggestion
                )
            )
            suggestion.target_id = entity_id
        else:
            raise KnowledgeGovernanceValidationError(
                "Unsupported suggestion approval target"
            )
        db.add(
            KnowledgeChangeEvent(
                entity_type=entity_type,
                entity_id=entity_id,
                action=suggestion.action,
                actor_id=actor.id,
                suggestion_id=suggestion.id,
                before_json=before_json,
                after_json=after_json,
            )
        )
    elif decision != "rejected":
        raise KnowledgeGovernanceValidationError("Invalid suggestion decision")

    suggestion.status = decision
    suggestion.reviewer_id = actor.id
    suggestion.decision_reason = normalized_reason
    suggestion.decided_at = datetime.now(timezone.utc)
    await db.flush()
    return suggestion


async def decide_knowledge_suggestions_bulk(
    db: AsyncSession,
    *,
    actor: User,
    suggestion_ids: list[str],
    decision: str,
    reason: str,
) -> list[KnowledgeSuggestion]:
    if not suggestion_ids or len(suggestion_ids) > 100:
        raise KnowledgeGovernanceValidationError(
            "Select between 1 and 100 knowledge suggestions"
        )
    if len(suggestion_ids) != len(set(suggestion_ids)):
        raise KnowledgeGovernanceValidationError("Suggestion IDs must be unique")
    if decision not in {"approved", "rejected"}:
        raise KnowledgeGovernanceValidationError("Invalid suggestion decision")
    if not reason.strip():
        raise KnowledgeGovernanceValidationError("Decision reason is required")

    async with db.begin_nested():
        suggestions = [
            await _get_suggestion_for_decision(db, suggestion_id=suggestion_id)
            for suggestion_id in suggestion_ids
        ]
        for suggestion in suggestions:
            if suggestion.status != "pending":
                raise KnowledgeGovernanceConflictError(
                    "Knowledge suggestion already decided"
                )
            if not await _can_review_suggestion(db, actor=actor, suggestion=suggestion):
                raise KnowledgeGovernancePermissionError(
                    "Knowledge suggestion review denied"
                )
        decided = [
            await decide_knowledge_suggestion(
                db,
                actor=actor,
                suggestion_id=suggestion.id,
                decision=decision,
                reason=reason,
            )
            for suggestion in suggestions
        ]
    return decided


async def submit_research_object_direction_suggestion(
    db: AsyncSession,
    *,
    actor: User,
    direction_id: str,
    research_object_id: str,
    relation_type: str,
    reason: str,
) -> KnowledgeSuggestion:
    await _require_active_direction(db, direction_id=direction_id)
    research_object = await db.get(ResearchObject, research_object_id)
    if research_object is None or research_object.created_by != actor.id:
        raise KnowledgeGovernanceNotFoundError("Research object not found")

    existing_link = await db.scalar(
        select(ResearchObjectDirection.id).where(
            ResearchObjectDirection.research_object_id == research_object_id,
            ResearchObjectDirection.direction_id == direction_id,
            ResearchObjectDirection.relation_type == relation_type,
        )
    )
    if existing_link is not None:
        raise KnowledgeGovernanceConflictError(
            "Research object direction relation already exists"
        )

    pending_suggestions = list(
        (
            await db.scalars(
                select(KnowledgeSuggestion).where(
                    KnowledgeSuggestion.target_type == "research_object_direction_link",
                    KnowledgeSuggestion.action == "link",
                    KnowledgeSuggestion.status == "pending",
                )
            )
        ).all()
    )
    if any(
        suggestion.payload_json.get("research_object_id") == research_object_id
        and suggestion.payload_json.get("direction_id") == direction_id
        and suggestion.payload_json.get("relation_type") == relation_type
        for suggestion in pending_suggestions
    ):
        raise KnowledgeGovernanceConflictError(
            "Research object direction suggestion already pending"
        )

    suggestion = KnowledgeSuggestion(
        target_type="research_object_direction_link",
        action="link",
        payload_json={
            "research_object_id": research_object_id,
            "direction_id": direction_id,
            "relation_type": relation_type,
            "reason": reason.strip(),
        },
        evidence_json={},
        submitted_by=actor.id,
        submitted_by_type="human",
    )
    db.add(suggestion)
    await db.flush()
    return suggestion


async def submit_research_object_direction_create_suggestion(
    db: AsyncSession,
    *,
    actor: User,
    research_object_id: str,
    name: str,
    reason: str,
) -> KnowledgeSuggestion:
    research_object = await db.get(ResearchObject, research_object_id)
    if research_object is None or research_object.created_by != actor.id:
        raise KnowledgeGovernanceNotFoundError("Research object not found")

    display_name = " ".join(name.split())
    normalized_name = display_name.casefold()
    normalized_reason = reason.strip()
    if not display_name or not normalized_reason:
        raise KnowledgeGovernanceValidationError("Direction name and reason are required")

    existing_direction = await db.scalar(
        select(ResearchDirection.id).where(
            ResearchDirection.normalized_name == normalized_name,
            ResearchDirection.status == "active",
        )
    )
    if existing_direction is not None:
        raise KnowledgeGovernanceConflictError("Research direction name already exists")

    pending_suggestions = list(
        (
            await db.scalars(
                select(KnowledgeSuggestion).where(
                    KnowledgeSuggestion.target_type == "research_direction",
                    KnowledgeSuggestion.action == "create",
                    KnowledgeSuggestion.status == "pending",
                )
            )
        ).all()
    )
    if any(
        suggestion.payload_json.get("research_object_id") == research_object_id
        and " ".join(str(suggestion.payload_json.get("name", "")).split()).casefold()
        == normalized_name
        for suggestion in pending_suggestions
    ):
        raise KnowledgeGovernanceConflictError(
            "Research direction creation suggestion already pending"
        )

    suggestion = KnowledgeSuggestion(
        target_type="research_direction",
        action="create",
        payload_json={
            "research_object_id": research_object_id,
            "name": display_name,
            "reason": normalized_reason,
        },
        evidence_json={},
        submitted_by=actor.id,
        submitted_by_type="human",
    )
    db.add(suggestion)
    await db.flush()
    return suggestion
