from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.note import Note
from app.models.project import ResearcherProject
from app.models.session import Session
from app.models.source import Source, SourceShare
from app.models.user import User
from app.schemas.note import NoteCreate, NoteResponse, NoteUpdate
from app.services.sharing_service import (
    PERMISSION_READWRITE,
    SCOPE_ALL,
    SCOPE_PROJECT,
    build_source_response_fields,
    can_user_edit_source,
)

router = APIRouter(prefix="/notes", tags=["notes"])


async def _build_note_response(
    note: Note, user: User, db: AsyncSession
) -> NoteResponse:
    """Build a NoteResponse with sharing info from the linked source (if any)."""
    resp = NoteResponse.model_validate(note)

    # Find if there is a source of type='note' linked to this note
    result = await db.execute(
        select(Source)
        .options(
            selectinload(Source.share).selectinload(SourceShare.sharer),
            selectinload(Source.owner),
        )
        .where(Source.note_id == note.id)
    )
    source = result.scalar_one_or_none()
    if source:
        extra = build_source_response_fields(source, user.id)
        resp.owner_id = extra["owner_id"]
        resp.owner_name = extra["owner_name"]
        resp.share = extra["share"]
        resp.is_shared = extra["is_shared"]
        resp.can_edit = extra["can_edit"]
    else:
        # Note without a source link: owned by session owner
        session_result = await db.execute(
            select(Session).where(Session.id == note.session_id)
        )
        session = session_result.scalar_one_or_none()
        if session and session.workspace_id == user.workspace.id:
            resp.can_edit = True

    return resp


@router.get("", response_model=list[NoteResponse])
async def list_notes(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    workspace = user.workspace

    # Own note IDs (from user's sessions)
    own_ids = (
        select(Note.id)
        .join(Session, Note.session_id == Session.id)
        .where(Session.workspace_id == workspace.id)
    )

    # Shared note IDs (via source type='note' with share)
    user_project_ids = select(ResearcherProject.project_id).where(
        ResearcherProject.researcher_id == user.id
    )
    shared_note_ids = (
        select(Source.note_id)
        .join(SourceShare, SourceShare.source_id == Source.id)
        .where(
            Source.type == "note",
            Source.note_id.isnot(None),
            or_(
                SourceShare.scope == SCOPE_ALL,
                SourceShare.project_id.in_(user_project_ids),
            ),
        )
    )

    # Combine own + shared note IDs, then load full Note objects
    combined_ids = own_ids.union(select(Note.id).where(Note.id.in_(shared_note_ids)))
    result = await db.execute(
        select(Note).where(Note.id.in_(combined_ids)).order_by(Note.created_at.desc())
    )
    notes = result.scalars().all()

    responses = []
    for n in notes:
        responses.append(await _build_note_response(n, user, db))
    return responses


@router.get(
    "/sessions/{session_id}",
    response_model=list[NoteResponse],
)
async def list_session_notes(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Note).where(Note.session_id == session_id)
    )
    notes = result.scalars().all()
    responses = []
    for n in notes:
        responses.append(await _build_note_response(n, user, db))
    return responses


@router.post("", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
async def create_note(
    body: NoteCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    note = Note(
        session_id=body.session_id,
        message_id=body.message_id,
        content=body.content,
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return await _build_note_response(note, user, db)


@router.put("/{note_id}", response_model=NoteResponse)
async def update_note(
    note_id: str,
    body: NoteUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Note).where(Note.id == note_id))
    note = result.scalar_one_or_none()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    # Check permission: session owner can always edit; shared readwrite can edit
    session_result = await db.execute(
        select(Session).where(Session.id == note.session_id)
    )
    session = session_result.scalar_one_or_none()
    is_owner = session and session.workspace_id == user.workspace.id

    if not is_owner:
        # Check if note has a shared source with readwrite
        source_result = await db.execute(
            select(Source).where(Source.note_id == note_id)
        )
        source = source_result.scalar_one_or_none()
        if not source or not await can_user_edit_source(user.id, source.id, db):
            raise HTTPException(status_code=403, detail="You don't have permission to edit this note")

    note.content = body.content
    await db.commit()
    await db.refresh(note)
    return await _build_note_response(note, user, db)


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    note_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Note).where(Note.id == note_id))
    note = result.scalar_one_or_none()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    # Only session owner can delete
    session_result = await db.execute(
        select(Session).where(Session.id == note.session_id)
    )
    session = session_result.scalar_one_or_none()
    if not session or session.workspace_id != user.workspace.id:
        raise HTTPException(status_code=403, detail="Only the owner can delete this note")

    await db.delete(note)
    await db.commit()
    return None
