from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.constants import ROLE_ADMIN, ROLE_PI
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.message import Message
from app.models.project import ResearcherProject
from app.models.research_asset import ProjectAssetLink, ResearchAsset
from app.models.research_object import ResearchObject
from app.models.session import Session
from app.models.source import SessionSource, Source, SourceShare
from app.models.tag import SessionTag
from app.models.user import User, Workspace
from app.schemas.research_object import ResearchObjectResponse
from app.schemas.session import SessionCreate, SessionResponse, SessionUpdate
from app.schemas.source import AvailableSourceResponse, SourceResponse
from app.services.research_asset_service import can_user_discover_asset
from app.services.activity_service import log_activity
from app.services.research_context import collect_project_source_ids
from app.services.sharing_service import build_source_response_fields, can_user_access_source
from app.services.task_service import UnknownTaskDefinitionError, get_task_definition

router = APIRouter(prefix="/sessions", tags=["sessions"])


PRIVILEGED_ROLES = (ROLE_ADMIN, ROLE_PI)


async def _can_view_all_project_sessions(
    project_id: str, user: User, db: AsyncSession
) -> bool:
    """Project owners and privileged roles may view every session in a project."""
    if user.role in PRIVILEGED_ROLES:
        return True
    result = await db.execute(
        select(ResearcherProject.id).where(
            ResearcherProject.project_id == project_id,
            ResearcherProject.researcher_id == user.id,
            ResearcherProject.role == "owner",
        )
    )
    return result.scalar_one_or_none() is not None


@router.get("", response_model=list[SessionResponse])
async def list_sessions(
    tag: str | None = None,
    project_id: str | None = None,
    include_empty: bool = False,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    workspace = user.workspace
    msg_count = func.count(Message.id).label("message_count")
    see_all_project_sessions = project_id is not None and (
        await _can_view_all_project_sessions(project_id, user, db)
    )
    query = (
        select(Session, msg_count, User.id, User.display_name, User.username)
        .outerjoin(Message, Message.session_id == Session.id)
        .join(Workspace, Workspace.id == Session.workspace_id)
        .join(User, User.id == Workspace.researcher_id)
        .group_by(Session.id, User.id)
    )
    if not see_all_project_sessions:
        # Members only see sessions they created; owners/privileged see all.
        query = query.where(Session.workspace_id == workspace.id)
    if tag:
        query = query.join(SessionTag).where(SessionTag.tag_id == tag)
    if project_id is not None:
        query = query.where(Session.project_id == project_id)
    if not include_empty:
        query = query.having(msg_count > 0)
    query = query.order_by(Session.created_at.desc())
    result = await db.execute(query)
    rows = result.all()
    return [
        SessionResponse(
            id=session.id,
            workspace_id=session.workspace_id,
            project_id=session.project_id,
            title=session.title,
            task_id=session.task_id,
            conversation_summary=session.conversation_summary,
            created_at=session.created_at,
            message_count=count,
            owner_id=owner_id,
            owner_name=display_name or username,
        )
        for session, count, owner_id, display_name, username in rows
    ]


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    body: SessionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    workspace = user.workspace
    if body.task_id is not None:
        try:
            await get_task_definition(
                body.task_id,
                db,
                project_id=body.project_id,
            )
        except UnknownTaskDefinitionError as exc:
            raise HTTPException(status_code=404, detail="Task not found") from exc

    session = Session(
        workspace_id=workspace.id,
        title=body.title,
        project_id=body.project_id,
        task_id=body.task_id,
    )
    db.add(session)
    await db.flush()

    if body.tag_ids:
        for tag_id in body.tag_ids:
            db.add(SessionTag(session_id=session.id, tag_id=tag_id))

    if session.project_id:
        source_ids = await collect_project_source_ids(
            db=db,
            project_id=session.project_id,
            user=user,
        )
        for source_id in source_ids:
            await _ensure_session_source_link(session.id, source_id, db)

        await log_activity(
            db,
            project_id=session.project_id,
            actor_id=user.id,
            action="session_created",
            target_type="session",
            target_id=session.id,
            target_title=session.title,
        )

    await db.commit()
    await db.refresh(session)
    return SessionResponse.model_validate(session)


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _get_session_for_user(session_id, user, db)
    count_result = await db.execute(
        select(func.count(Message.id)).where(Message.session_id == session_id)
    )
    msg_count = count_result.scalar() or 0
    return SessionResponse(
        id=session.id,
        workspace_id=session.workspace_id,
        project_id=session.project_id,
        title=session.title,
        task_id=session.task_id,
        conversation_summary=session.conversation_summary,
        created_at=session.created_at,
        message_count=msg_count,
    )


@router.get("/{session_id}/available-sources", response_model=list[AvailableSourceResponse])
async def list_session_available_sources(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _get_session_for_user(session_id, user, db)
    linked_source_ids = set(
        await db.scalars(
            select(SessionSource.source_id).where(SessionSource.session_id == session_id)
        )
    )

    result = await db.execute(
        select(ResearchAsset)
        .where(
            ResearchAsset.source_id.is_not(None),
            ResearchAsset.publication_status == "active",
        )
        .order_by(ResearchAsset.updated_at.desc(), ResearchAsset.id.desc())
    )

    responses: list[AvailableSourceResponse] = []
    seen_source_ids: set[str] = set()
    for asset in result.scalars().all():
        source_id = asset.source_id
        if not source_id or source_id in linked_source_ids or source_id in seen_source_ids:
            continue
        if not await can_user_discover_asset(db, user, asset):
            continue

        category = await _categorize_available_source(db, session.project_id, user, asset)
        if category is None:
            continue

        source = await db.scalar(
            select(Source)
            .options(
                selectinload(Source.share).selectinload(SourceShare.sharer),
                selectinload(Source.owner),
            )
            .where(Source.id == source_id)
        )
        if source is None:
            continue

        source_response = SourceResponse.model_validate(source)
        for key, value in build_source_response_fields(source, user.id).items():
            setattr(source_response, key, value)

        responses.append(
            AvailableSourceResponse(category=category, source=source_response)
        )
        seen_source_ids.add(source_id)

    return responses


@router.get("/{session_id}/research-objects", response_model=list[ResearchObjectResponse])
async def list_session_research_objects(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_session_for_user(session_id, user, db)

    result = await db.execute(
        select(ResearchObject).order_by(ResearchObject.created_at.desc())
    )
    items = [
        item
        for item in result.scalars().all()
        if item.content_json.get("session_id") == session_id
    ]
    return [
        ResearchObjectResponse(
            **(
                ResearchObjectResponse.model_validate(item).model_dump()
                | {
                    "session_id": item.content_json.get("session_id"),
                    "message_id": item.content_json.get("source_message_id"),
                }
            )
        )
        for item in items
    ]


@router.put("/{session_id}", response_model=SessionResponse)
async def update_session(
    session_id: str,
    body: SessionUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _get_session_for_user(session_id, user, db, write=True)
    if body.title is not None:
        session.title = body.title
    if body.tag_ids is not None:
        # Replace all tags
        result = await db.execute(
            select(SessionTag).where(SessionTag.session_id == session.id)
        )
        for st in result.scalars().all():
            await db.delete(st)
        for tag_id in body.tag_ids:
            db.add(SessionTag(session_id=session.id, tag_id=tag_id))
    await db.commit()
    await db.refresh(session)
    return SessionResponse.model_validate(session)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _get_session_for_user(session_id, user, db, write=True)
    await db.delete(session)
    await db.commit()
    return None


async def _get_session_for_user(
    session_id: str, user: User, db: AsyncSession, write: bool = False
) -> Session:
    result = await db.execute(
        select(Session).where(
            Session.id == session_id,
            Session.workspace_id == user.workspace.id,
        )
    )
    session = result.scalar_one_or_none()
    if session is not None:
        return session
    # Read access extends to project owners and privileged roles; writes
    # (rename/delete) stay restricted to the session creator.
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()
    if (
        not write
        and session is not None
        and session.project_id is not None
        and await _can_view_all_project_sessions(session.project_id, user, db)
    ):
        return session
    raise HTTPException(status_code=404, detail="Session not found")


async def _categorize_available_source(
    db: AsyncSession,
    project_id: str | None,
    user: User,
    asset: ResearchAsset,
) -> str | None:
    if project_id:
        project_link = await db.scalar(
            select(ProjectAssetLink).where(
                ProjectAssetLink.asset_id == asset.id,
                ProjectAssetLink.project_id == project_id,
            )
        )
        if project_link is not None:
            return "project"
    if asset.visibility_scope == "lab_public":
        return "lab_public"
    if asset.owner_id == user.id and asset.visibility_scope != "lab_private":
        return "my_materials"
    return None


async def _ensure_session_source_link(
    session_id: str,
    source_id: str,
    db: AsyncSession,
) -> None:
    existing = await db.scalar(
        select(SessionSource).where(
            SessionSource.session_id == session_id,
            SessionSource.source_id == source_id,
        )
    )
    if existing is None:
        db.add(SessionSource(session_id=session_id, source_id=source_id))
