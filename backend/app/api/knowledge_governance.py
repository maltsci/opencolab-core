from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.constants import ROLE_ADMIN, ROLE_PI
from app.core.dependencies import get_current_user, require_role
from app.models.user import User
from app.schemas.knowledge_governance import (
    DirectionStewardResponse,
    BulkSuggestionDecision,
    GroupStewardResponse,
    KnowledgeInboxDecisionsReadResponse,
    KnowledgeInboxResponse,
    KnowledgeHealthResponse,
    KnowledgeReviewCapabilityResponse,
    KnowledgeSuggestionAuditResponse,
    KnowledgeSuggestionCreate,
    KnowledgeSuggestionResponse,
    SuggestionDecision,
    StewardAssignmentCreate,
)
from app.services.knowledge_governance_service import (
    KnowledgeGovernanceConflictError,
    KnowledgeGovernanceNotFoundError,
    KnowledgeGovernancePermissionError,
    KnowledgeGovernanceValidationError,
    assign_direction_steward,
    assign_group_steward,
    can_review_knowledge_suggestions,
    list_direction_stewards,
    list_group_stewards,
    list_knowledge_suggestions,
    revoke_direction_steward,
    revoke_group_steward,
    decide_knowledge_suggestion,
    decide_knowledge_suggestions_bulk,
    get_knowledge_suggestion,
    get_knowledge_suggestion_audit,
    get_knowledge_inbox,
    get_knowledge_health,
    mark_knowledge_inbox_decisions_seen,
    submit_knowledge_suggestion,
)
from app.services.research_group_service import ResearchGroupNotFoundError


router = APIRouter(prefix="/knowledge-governance", tags=["knowledge-governance"])
knowledge_health_access = require_role(ROLE_ADMIN, ROLE_PI)


def _raise_http_error(exc: Exception) -> None:
    if isinstance(exc, (KnowledgeGovernanceNotFoundError, ResearchGroupNotFoundError)):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, KnowledgeGovernancePermissionError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, KnowledgeGovernanceConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, KnowledgeGovernanceValidationError):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    raise RuntimeError("Unknown knowledge governance service error") from exc


@router.post(
    "/groups/{group_id}/stewards",
    response_model=GroupStewardResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_group_steward(
    group_id: str,
    body: StewardAssignmentCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        assignment = await assign_group_steward(
            db,
            actor=user,
            group_id=group_id,
            user_id=body.user_id,
        )
        await db.commit()
        await db.refresh(assignment)
        return assignment
    except (
        KnowledgeGovernanceConflictError,
        KnowledgeGovernanceNotFoundError,
        KnowledgeGovernancePermissionError,
        ResearchGroupNotFoundError,
    ) as exc:
        _raise_http_error(exc)


@router.get("/groups/{group_id}/stewards", response_model=list[GroupStewardResponse])
async def get_group_stewards(
    group_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await list_group_stewards(db, actor=user, group_id=group_id)
    except (
        KnowledgeGovernanceNotFoundError,
        KnowledgeGovernancePermissionError,
        ResearchGroupNotFoundError,
    ) as exc:
        _raise_http_error(exc)


@router.delete(
    "/groups/{group_id}/stewards/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_group_steward(
    group_id: str,
    user_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await revoke_group_steward(
            db,
            actor=user,
            group_id=group_id,
            user_id=user_id,
        )
        await db.commit()
        return None
    except (
        KnowledgeGovernanceNotFoundError,
        KnowledgeGovernancePermissionError,
        ResearchGroupNotFoundError,
    ) as exc:
        _raise_http_error(exc)


@router.post(
    "/directions/{direction_id}/stewards",
    response_model=DirectionStewardResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_direction_steward(
    direction_id: str,
    body: StewardAssignmentCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        assignment = await assign_direction_steward(
            db,
            actor=user,
            direction_id=direction_id,
            user_id=body.user_id,
        )
        await db.commit()
        await db.refresh(assignment)
        return assignment
    except (
        KnowledgeGovernanceConflictError,
        KnowledgeGovernanceNotFoundError,
        KnowledgeGovernancePermissionError,
    ) as exc:
        _raise_http_error(exc)


@router.get(
    "/directions/{direction_id}/stewards",
    response_model=list[DirectionStewardResponse],
)
async def get_direction_stewards(
    direction_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await list_direction_stewards(
            db,
            actor=user,
            direction_id=direction_id,
        )
    except (
        KnowledgeGovernanceConflictError,
        KnowledgeGovernanceNotFoundError,
        KnowledgeGovernancePermissionError,
    ) as exc:
        _raise_http_error(exc)


@router.delete(
    "/directions/{direction_id}/stewards/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_direction_steward(
    direction_id: str,
    user_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await revoke_direction_steward(
            db,
            actor=user,
            direction_id=direction_id,
            user_id=user_id,
        )
        await db.commit()
        return None
    except (
        KnowledgeGovernanceConflictError,
        KnowledgeGovernanceNotFoundError,
        KnowledgeGovernancePermissionError,
    ) as exc:
        _raise_http_error(exc)


@router.post(
    "/suggestions",
    response_model=KnowledgeSuggestionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_knowledge_suggestion(
    body: KnowledgeSuggestionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        suggestion = await submit_knowledge_suggestion(
            db,
            actor=user,
            target_type=body.target_type,
            target_id=body.target_id,
            action=body.action,
            payload_json=body.payload_json,
            evidence_json=body.evidence_json,
        )
        await db.commit()
        await db.refresh(suggestion)
        return suggestion
    except KnowledgeGovernanceValidationError as exc:
        _raise_http_error(exc)


@router.get("/suggestions", response_model=list[KnowledgeSuggestionResponse])
async def get_knowledge_suggestions(
    suggestion_status: str | None = Query(default=None, alias="status"),
    reviewable_only: bool = Query(default=False),
    limit: int = Query(default=20, ge=1, le=100),
    before_id: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await list_knowledge_suggestions(
            db,
            actor=user,
            suggestion_status=suggestion_status,
            limit=limit,
            before_id=before_id,
            reviewable_only=reviewable_only,
        )
    except KnowledgeGovernanceValidationError as exc:
        _raise_http_error(exc)


@router.get(
    "/review-capability",
    response_model=KnowledgeReviewCapabilityResponse,
)
async def get_knowledge_review_capability(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return KnowledgeReviewCapabilityResponse(
        can_review=await can_review_knowledge_suggestions(db, actor=user)
    )


@router.get("/inbox", response_model=KnowledgeInboxResponse)
async def get_knowledge_inbox_endpoint(
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_knowledge_inbox(db, actor=user, limit=limit)


@router.get("/health", response_model=KnowledgeHealthResponse)
async def get_knowledge_health_endpoint(
    user: User = Depends(knowledge_health_access),
    db: AsyncSession = Depends(get_db),
):
    return await get_knowledge_health(db)


@router.post(
    "/inbox/decisions/mark-read",
    response_model=KnowledgeInboxDecisionsReadResponse,
)
async def mark_knowledge_inbox_decisions_read(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    marked_count = await mark_knowledge_inbox_decisions_seen(db, actor=user)
    await db.commit()
    return KnowledgeInboxDecisionsReadResponse(marked_count=marked_count)


@router.get(
    "/suggestions/{suggestion_id}", response_model=KnowledgeSuggestionResponse
)
async def get_knowledge_suggestion_by_id(
    suggestion_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await get_knowledge_suggestion(
            db,
            actor=user,
            suggestion_id=suggestion_id,
        )
    except (
        KnowledgeGovernanceNotFoundError,
        KnowledgeGovernancePermissionError,
    ) as exc:
        _raise_http_error(exc)


@router.get(
    "/suggestions/{suggestion_id}/audit",
    response_model=KnowledgeSuggestionAuditResponse | None,
)
async def get_knowledge_suggestion_audit_endpoint(
    suggestion_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await get_knowledge_suggestion_audit(
            db,
            actor=user,
            suggestion_id=suggestion_id,
        )
    except (
        KnowledgeGovernanceNotFoundError,
        KnowledgeGovernancePermissionError,
    ) as exc:
        _raise_http_error(exc)


async def _decide_knowledge_suggestion(
    suggestion_id: str,
    body: SuggestionDecision,
    decision: str,
    user: User,
    db: AsyncSession,
):
    try:
        suggestion = await decide_knowledge_suggestion(
            db,
            actor=user,
            suggestion_id=suggestion_id,
            decision=decision,
            reason=body.reason,
        )
        await db.commit()
        await db.refresh(suggestion)
        return suggestion
    except (
        KnowledgeGovernanceConflictError,
        KnowledgeGovernanceNotFoundError,
        KnowledgeGovernancePermissionError,
        KnowledgeGovernanceValidationError,
    ) as exc:
        _raise_http_error(exc)


async def _decide_knowledge_suggestions_bulk(
    body: BulkSuggestionDecision,
    decision: str,
    user: User,
    db: AsyncSession,
):
    try:
        suggestions = await decide_knowledge_suggestions_bulk(
            db,
            actor=user,
            suggestion_ids=body.suggestion_ids,
            decision=decision,
            reason=body.reason,
        )
        await db.commit()
        for suggestion in suggestions:
            await db.refresh(suggestion)
        return suggestions
    except (
        KnowledgeGovernanceConflictError,
        KnowledgeGovernanceNotFoundError,
        KnowledgeGovernancePermissionError,
        KnowledgeGovernanceValidationError,
    ) as exc:
        await db.rollback()
        _raise_http_error(exc)


@router.post(
    "/suggestions/bulk/approve",
    response_model=list[KnowledgeSuggestionResponse],
)
async def approve_knowledge_suggestions_bulk(
    body: BulkSuggestionDecision,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _decide_knowledge_suggestions_bulk(body, "approved", user, db)


@router.post(
    "/suggestions/bulk/reject",
    response_model=list[KnowledgeSuggestionResponse],
)
async def reject_knowledge_suggestions_bulk(
    body: BulkSuggestionDecision,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _decide_knowledge_suggestions_bulk(body, "rejected", user, db)


@router.post(
    "/suggestions/{suggestion_id}/approve",
    response_model=KnowledgeSuggestionResponse,
)
async def approve_knowledge_suggestion(
    suggestion_id: str,
    body: SuggestionDecision,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _decide_knowledge_suggestion(
        suggestion_id,
        body,
        "approved",
        user,
        db,
    )


@router.post(
    "/suggestions/{suggestion_id}/reject",
    response_model=KnowledgeSuggestionResponse,
)
async def reject_knowledge_suggestion(
    suggestion_id: str,
    body: SuggestionDecision,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _decide_knowledge_suggestion(
        suggestion_id,
        body,
        "rejected",
        user,
        db,
    )
