from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ROLE_ADMIN, ROLE_PI
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.message import Message
from app.models.project import Project, ResearcherProject
from app.models.research_object import ResearchObject
from app.models.session import Session
from app.models.user import User
from app.schemas.research_object import (
    ResearchObjectCreate,
    ResearchObjectDirectionCreateSuggestionRequest,
    ResearchObjectResponse,
    ResearchObjectUpdate,
)
from app.services.activity_service import log_activity
from app.services.research_asset_service import materialize_research_object_asset
from app.schemas.knowledge_governance import KnowledgeSuggestionResponse
from app.services.knowledge_governance_service import (
    KnowledgeGovernanceConflictError,
    KnowledgeGovernanceNotFoundError,
    KnowledgeGovernanceValidationError,
    submit_research_object_direction_create_suggestion,
)

router = APIRouter(prefix="/research-objects", tags=["research-objects"])


async def _get_session_for_user(session_id: str, user: User, db: AsyncSession):
    result = await db.execute(
        select(Session).where(
            Session.id == session_id,
            Session.workspace_id == user.workspace.id,
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


async def _get_project_for_user(project_id: str, user: User, db: AsyncSession) -> Project:
    project = await db.scalar(select(Project).where(Project.id == project_id))
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    if user.role in {ROLE_ADMIN, ROLE_PI}:
        return project

    membership = await db.scalar(
        select(ResearcherProject).where(
            ResearcherProject.project_id == project_id,
            ResearcherProject.researcher_id == user.id,
        )
    )
    if membership is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _build_response(
    research_object: ResearchObject,
    *,
    session_id: str | None = None,
    message_id: str | None = None,
    source_session_deleted: bool | None = None,
) -> ResearchObjectResponse:
    payload = ResearchObjectResponse.model_validate(research_object).model_dump()
    payload["session_id"] = (
        session_id
        or research_object.content_json.get("session_id")
        or research_object.content_json.get("source_session_id")
    )
    payload["message_id"] = message_id or research_object.content_json.get(
        "source_message_id"
    )
    if source_session_deleted is not None:
        payload["content_json"] = {
            **payload["content_json"],
            "source_session_deleted": source_session_deleted,
        }
    return ResearchObjectResponse(**payload)


async def _get_research_object_for_user(
    research_object_id: str,
    user: User,
    db: AsyncSession,
) -> ResearchObject:
    result = await db.execute(
        select(ResearchObject).where(
            ResearchObject.id == research_object_id,
            ResearchObject.created_by == user.id,
        )
    )
    research_object = result.scalar_one_or_none()
    if research_object is None:
        raise HTTPException(status_code=404, detail="Research object not found")
    return research_object


@router.post("", response_model=ResearchObjectResponse, status_code=status.HTTP_201_CREATED)
async def create_research_object(
    body: ResearchObjectCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _get_session_for_user(body.session_id, user, db)

    if body.message_id is not None:
        message_result = await db.execute(
            select(Message).where(
                Message.id == body.message_id,
                Message.session_id == session.id,
            )
        )
        if message_result.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="Message not found")

    research_object = ResearchObject(
        type=body.type,
        title=body.title,
        content=body.content,
        content_json={
            **body.content_json,
            "project_id": session.project_id,
            "session_id": session.id,
            "source_session_id": session.id,
            "source_message_id": body.message_id,
        },
        created_by=user.id,
    )
    db.add(research_object)
    await db.flush()
    await materialize_research_object_asset(
        db=db,
        research_object=research_object,
        owner_id=user.id,
        origin_project_id=session.project_id,
        origin_session_id=session.id,
        visibility_scope="project" if session.project_id else "private",
        link_type="memory",
    )
    if session.project_id:
        await log_activity(
            db,
            project_id=session.project_id,
            actor_id=user.id,
            action="memory_saved",
            target_type="research_object",
            target_id=research_object.id,
            target_title=research_object.title,
        )
    await db.commit()
    await db.refresh(research_object)
    return _build_response(
        research_object,
        session_id=session.id,
        message_id=body.message_id,
    )


@router.post(
    "/{research_object_id}/direction-suggestions",
    response_model=KnowledgeSuggestionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_research_object_direction_create_suggestion(
    research_object_id: str,
    body: ResearchObjectDirectionCreateSuggestionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        suggestion = await submit_research_object_direction_create_suggestion(
            db,
            actor=user,
            research_object_id=research_object_id,
            name=body.name,
            reason=body.reason,
        )
        await db.commit()
        await db.refresh(suggestion)
        return suggestion
    except KnowledgeGovernanceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KnowledgeGovernanceConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except KnowledgeGovernanceValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get(
    "/sessions/{session_id}",
    response_model=list[ResearchObjectResponse],
)
async def list_research_objects_for_session(
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
    return [_build_response(item) for item in items]


@router.get(
    "/projects/{project_id}",
    response_model=list[ResearchObjectResponse],
)
async def list_research_objects_for_project(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_for_user(project_id, user, db)

    result = await db.execute(
        select(ResearchObject, Session.id)
        .outerjoin(
            Session,
            or_(
                Session.id == ResearchObject.content_json["source_session_id"].as_string(),
                Session.id == ResearchObject.content_json["session_id"].as_string(),
            ),
        )
        .where(
            or_(
                ResearchObject.content_json["project_id"].as_string() == project_id,
                Session.project_id == project_id,
            )
        )
        .order_by(ResearchObject.created_at.desc(), ResearchObject.id.desc())
    )

    responses: list[ResearchObjectResponse] = []
    for research_object, live_session_id in result.all():
        source_session_id = (
            research_object.content_json.get("source_session_id")
            or research_object.content_json.get("session_id")
        )
        responses.append(
            _build_response(
                research_object,
                source_session_deleted=bool(source_session_id and live_session_id is None),
            )
        )
    return responses


@router.put("/{research_object_id}", response_model=ResearchObjectResponse)
async def update_research_object(
    research_object_id: str,
    body: ResearchObjectUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    research_object = await _get_research_object_for_user(research_object_id, user, db)

    research_object.title = body.title
    research_object.content = body.content

    await db.commit()
    await db.refresh(research_object)
    return _build_response(research_object)


@router.delete("/{research_object_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_research_object(
    research_object_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    research_object = await _get_research_object_for_user(research_object_id, user, db)
    await db.delete(research_object)
    await db.commit()
    return None
