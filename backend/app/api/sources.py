import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, PlainTextResponse, Response
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.api.projects import _get_project_for_user
from app.services.activity_service import log_activity
from app.core.security import create_source_preview_token, decode_source_preview_token
from app.models.source import (
    Chunk,
    HiddenSource,
    SessionSource,
    Source,
    SourceMember,
    SourceShare,
    WorkspaceSource,
)
from app.models.source_annotation import SourceAnnotation
from app.models.session import Session
from app.models.trace import SourceExtraction
from app.models.user import User
from app.schemas.extraction import SourceExtractionResponse
from app.schemas.source import (
    AddMemberRequest,
    CreateGroupRequest,
    ShareSourceRequest,
    SourceMemberResponse,
    SourceResponse,
    UpdateShareRequest,
    UpdateSourceRequest,
    UpdateSessionSourceRequest,
    ZipUploadResponse,
)
from app.schemas.source_annotation import (
    SourceAnnotationCreate,
    SourceAnnotationResponse,
)
from app.services.source_group_service import resolve_leaf_sources, validate_add_member
from app.services.duplicate_upload_service import build_duplicate_upload_info
from app.services.file_storage import compute_file_hash, resolve_file_path, save_file
from app.services.research_asset_service import (
    materialize_source_asset,
    sync_source_share_to_asset,
)
from app.services.research_context import collect_project_source_ids
from app.services.sharing_service import (
    build_source_response_fields,
    can_user_access_source,
    can_user_download_source,
    can_user_edit_source,
    count_unshared_group_files,
    get_visible_sources,
    hide_source_for_user,
    share_source,
    unshare_source,
    update_share,
)
from app.services.vector_store import delete_vectors_by_source
from app.services.zip_service import extract_documents_from_zip

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sources"])


async def _ensure_source_preview_access(
    source_id: str,
    user: User,
    db: AsyncSession,
) -> None:
    if not await can_user_access_source(user.id, source_id, db):
        raise HTTPException(status_code=404, detail="Source not found")


def _annotation_response(
    annotation: SourceAnnotation,
    author_name: str | None,
    current_user_id: str,
) -> SourceAnnotationResponse:
    response = SourceAnnotationResponse.model_validate(annotation)
    response.author_name = author_name
    response.can_delete = annotation.created_by == current_user_id
    return response


async def _get_session_project_id(session_id: str | None, db: AsyncSession) -> str | None:
    if not session_id:
        return None
    return await db.scalar(select(Session.project_id).where(Session.id == session_id))


async def _load_extraction_statuses(
    db: AsyncSession,
    source_ids: list[str],
) -> dict[str, str]:
    if not source_ids:
        return {}

    result = await db.execute(
        select(SourceExtraction.source_id, SourceExtraction.status).where(
            SourceExtraction.source_id.in_(source_ids)
        )
    )
    return {source_id: status for source_id, status in result.all()}


async def _build_source_response(
    source: Source,
    current_user_id: str | None = None,
    *,
    extraction_status: str | None = None,
    display_name: str | None = None,
) -> SourceResponse:
    response = SourceResponse.model_validate(source)
    response.extraction_status = extraction_status

    if current_user_id is not None:
        extra = build_source_response_fields(source, current_user_id)
        for key, value in extra.items():
            setattr(response, key, value)

    if display_name:
        response.name = display_name

    return response


async def _build_source_responses(
    sources: list[Source],
    db: AsyncSession,
    current_user_id: str | None = None,
    *,
    display_names: dict[str, str | None] | None = None,
) -> list[SourceResponse]:
    status_map = await _load_extraction_statuses(db, [source.id for source in sources])

    responses: list[SourceResponse] = []
    for source in sources:
        responses.append(
            await _build_source_response(
                source,
                current_user_id,
                extraction_status=status_map.get(source.id),
                display_name=display_names.get(source.id) if display_names else None,
            )
        )
    return responses


@router.get(
    "/sessions/{session_id}/sources", response_model=list[SourceResponse]
)
async def list_session_sources(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project_id = await _get_session_project_id(session_id, db)
    if project_id:
        source_ids = await collect_project_source_ids(
            db=db,
            project_id=project_id,
            user=user,
        )
        for source_id in source_ids:
            await _ensure_session_link(session_id, source_id, db)
        await db.flush()

    result = await db.execute(
        select(Source, SessionSource.display_name)
        .join(SessionSource, SessionSource.source_id == Source.id)
        .where(SessionSource.session_id == session_id)
        .options(
            selectinload(Source.share).selectinload(SourceShare.sharer),
            selectinload(Source.owner),
        )
    )
    rows = result.unique().all()
    sources = [source for source, _display_name in rows]
    display_names = {source.id: display_name for source, display_name in rows}
    return await _build_source_responses(
        sources,
        db,
        user.id,
        display_names=display_names,
    )


@router.post(
    "/sessions/{session_id}/sources",
    response_model=SourceResponse | ZipUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_source(
    session_id: str,
    file: UploadFile | None = None,
    source_id: str | None = Form(None),
    upload_kind: str | None = Form(None),
    meta_title: str | None = Form(None),
    meta_description: str | None = Form(None),
    meta_tags: str | None = Form(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    workspace = user.workspace

    if file:
        try:
            filename = file.filename or ""
            if upload_kind == "data_package":
                return await _handle_file_upload(
                    file, session_id, workspace.id, db, owner_id=user.id,
                    upload_kind=upload_kind,
                    meta_title=meta_title,
                    meta_description=meta_description,
                    meta_tags=meta_tags,
                )
            if filename.lower().endswith(".zip"):
                content = await file.read()
                return await _handle_zip_upload(
                    content, db, session_id=session_id, workspace_id=workspace.id,
                    owner_id=user.id,
                )
            return await _handle_file_upload(
                file, session_id, workspace.id, db, owner_id=user.id
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("File upload failed")
            raise HTTPException(status_code=500, detail=f"File processing failed: {e}")
    elif source_id:
        return await _link_existing_source(source_id, session_id, workspace.id, db)
    else:
        raise HTTPException(status_code=400, detail="Provide a file or source_id")


@router.delete(
    "/sessions/{session_id}/sources/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def unlink_source(
    session_id: str,
    source_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SessionSource).where(
            SessionSource.session_id == session_id,
            SessionSource.source_id == source_id,
        )
    )
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Source not linked to session")
    await db.delete(link)
    await db.commit()
    return None


@router.patch(
    "/sessions/{session_id}/sources/{source_id}",
    response_model=SourceResponse,
)
async def update_session_source(
    session_id: str,
    source_id: str,
    body: UpdateSessionSourceRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Set a session-local display name for a source (alias, does not affect global source name)."""
    result = await db.execute(
        select(SessionSource, Source)
        .join(Source, Source.id == SessionSource.source_id)
        .where(
            SessionSource.session_id == session_id,
            SessionSource.source_id == source_id,
        )
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Source not linked to session")
    link, source = row
    link.display_name = body.display_name.strip() or None
    await db.commit()
    await db.refresh(source)
    status_map = await _load_extraction_statuses(db, [source.id])
    resp = await _build_source_response(
        source,
        user.id,
        extraction_status=status_map.get(source.id),
        display_name=link.display_name,
    )
    return resp


@router.get("/sources/{source_id}", response_model=SourceResponse)
async def get_source(
    source_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not await can_user_access_source(user.id, source_id, db):
        raise HTTPException(status_code=404, detail="Source not found")
    result = await db.execute(
        select(Source)
        .options(
            selectinload(Source.share).selectinload(SourceShare.sharer),
            selectinload(Source.owner),
        )
        .where(Source.id == source_id)
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    status_map = await _load_extraction_statuses(db, [source.id])
    return await _build_source_response(
        source,
        user.id,
        extraction_status=status_map.get(source.id),
    )


@router.get(
    "/sources/{source_id}/extraction",
    response_model=SourceExtractionResponse,
)
async def get_source_extraction(
    source_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not await can_user_access_source(user.id, source_id, db):
        raise HTTPException(status_code=404, detail="Source not found")

    result = await db.execute(
        select(SourceExtraction).where(SourceExtraction.source_id == source_id)
    )
    extraction = result.scalar_one_or_none()
    if extraction is None:
        raise HTTPException(status_code=404, detail="Source extraction not found")
    return SourceExtractionResponse.model_validate(extraction)


async def _get_user_from_token_param(
    source_id: str,
    token: str,
    db: AsyncSession,
) -> User:
    """Authenticate user from a scoped preview token for iframe/img src URLs."""
    from sqlalchemy.orm import selectinload

    user_id = decode_source_preview_token(token, source_id)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    result = await db.execute(
        select(User).options(selectinload(User.workspace)).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user


@router.get("/sources/{source_id}/preview-token")
async def create_source_preview_token_endpoint(
    source_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a short-lived token for browser-native source previews."""
    if not await can_user_access_source(user.id, source_id, db):
        raise HTTPException(status_code=404, detail="Source not found")
    return {
        "token": create_source_preview_token(user.id, source_id),
        "expires_in": 300,
    }


@router.get(
    "/sources/{source_id}/annotations",
    response_model=list[SourceAnnotationResponse],
)
async def list_source_annotations(
    source_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return shared annotations only to users allowed to preview the source."""
    await _ensure_source_preview_access(source_id, user, db)
    result = await db.execute(
        select(SourceAnnotation, User.display_name, User.username)
        .outerjoin(User, User.id == SourceAnnotation.created_by)
        .where(SourceAnnotation.source_id == source_id)
        .order_by(SourceAnnotation.start_offset, SourceAnnotation.created_at)
    )
    return [
        _annotation_response(annotation, display_name or username, user.id)
        for annotation, display_name, username in result.all()
    ]


@router.post(
    "/sources/{source_id}/annotations",
    response_model=SourceAnnotationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_source_annotation(
    source_id: str,
    body: SourceAnnotationCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a shared text annotation for a source the user may preview."""
    await _ensure_source_preview_access(source_id, user, db)
    annotation = SourceAnnotation(
        source_id=source_id,
        created_by=user.id,
        selected_text=body.selected_text,
        start_offset=body.start_offset,
        end_offset=body.end_offset,
        note=body.note,
    )
    db.add(annotation)
    await db.commit()
    await db.refresh(annotation)
    return _annotation_response(annotation, user.display_name or user.username, user.id)


@router.delete(
    "/sources/{source_id}/annotations/{annotation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_source_annotation(
    source_id: str,
    annotation_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _ensure_source_preview_access(source_id, user, db)
    annotation = await db.scalar(
        select(SourceAnnotation).where(
            SourceAnnotation.id == annotation_id,
            SourceAnnotation.source_id == source_id,
        )
    )
    if annotation is None:
        raise HTTPException(status_code=404, detail="Annotation not found")
    if annotation.created_by != user.id:
        raise HTTPException(status_code=403, detail="Only the author can delete this annotation")
    await db.delete(annotation)
    await db.commit()
    return None


@router.get("/sources/{source_id}/file")
async def get_source_file(
    source_id: str,
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """Serve the raw file for a source."""
    token_user = await _get_user_from_token_param(source_id, token, db)
    if not await can_user_download_source(
        user=token_user,
        source_id=source_id,
        db=db,
    ):
        raise HTTPException(status_code=403, detail="Access denied")

    result = await db.execute(select(Source).where(Source.id == source_id))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    if source.type not in {"file", "data_package"} or not source.content_path:
        raise HTTPException(status_code=400, detail="Source has no file")

    try:
        file_path = resolve_file_path(source.content_path)
    except ValueError:
        logger.warning("Rejected unsafe content path for source %s", source_id)
        raise HTTPException(status_code=404, detail="File not found on disk")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        media_type = "application/pdf"
    elif suffix in {".md", ".markdown", ".txt"}:
        media_type = "text/plain; charset=utf-8"
    else:
        media_type = "application/octet-stream"
    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=source.name,
        content_disposition_type="inline",
    )


@router.get("/sources/{source_id}/text")
async def get_source_text(
    source_id: str,
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """Serve reading text while preserving original parser Markdown when available."""
    token_user = await _get_user_from_token_param(source_id, token, db)
    if not await can_user_access_source(token_user.id, source_id, db):
        raise HTTPException(status_code=403, detail="Access denied")

    extraction = await db.scalar(
        select(SourceExtraction).where(SourceExtraction.source_id == source_id)
    )
    rendered_markdown = (extraction.rendered_markdown or "").strip() if extraction else ""
    if rendered_markdown:
        return PlainTextResponse(rendered_markdown)

    result = await db.execute(
        select(Chunk.text)
        .where(Chunk.source_id == source_id)
        .order_by(Chunk.chunk_index, Chunk.id)
    )
    texts = [row[0] for row in result.all() if row[0]]
    if not texts:
        raise HTTPException(status_code=404, detail="No extracted text available")
    return PlainTextResponse("\n\n".join(texts))


@router.get("/sources/{source_id}/thumbnail")
async def get_source_thumbnail(
    source_id: str,
    token: str,
    page: int = Query(default=1, ge=1),
    db: AsyncSession = Depends(get_db),
):
    """Render a PDF page as a PNG thumbnail."""
    token_user = await _get_user_from_token_param(source_id, token, db)
    if not await can_user_access_source(token_user.id, source_id, db):
        raise HTTPException(status_code=403, detail="Access denied")

    result = await db.execute(select(Source).where(Source.id == source_id))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    if source.type != "file" or not source.content_path:
        raise HTTPException(status_code=400, detail="Source has no file")

    try:
        file_path = resolve_file_path(source.content_path)
    except ValueError:
        logger.warning("Rejected unsafe content path for source thumbnail %s", source_id)
        raise HTTPException(status_code=404, detail="File not found on disk")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    try:
        import fitz  # PyMuPDF

        with fitz.open(str(file_path)) as doc:
            page_count = len(doc)
            if page > page_count:
                raise HTTPException(status_code=404, detail="PDF page not found")
            pdf_page = doc[page - 1]
            # Render at 1.5x zoom for decent quality thumbnail
            mat = fitz.Matrix(1.5, 1.5)
            pix = pdf_page.get_pixmap(matrix=mat)
            png_bytes = pix.tobytes("png")
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Failed to generate thumbnail for source %s: %s", source_id, e)
        raise HTTPException(status_code=500, detail="Failed to generate thumbnail")

    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=3600",
            "X-PDF-Page-Count": str(page_count),
        },
    )


@router.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(
    source_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Source).options(selectinload(Source.share)).where(Source.id == source_id)
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    is_owner = source.owner_id == user.id
    is_shared = source.share is not None

    if source.type == "file":
        if is_shared:
            # Shared file: soft-delete (hide for current user)
            await hide_source_for_user(user.id, source_id, db)
            await db.commit()
            return None
        elif is_owner or source.owner_id is None:
            # Unshared file owned by user: actual delete
            delete_vectors_by_source(source_id)
            await db.delete(source)
            await db.commit()
            return None
        else:
            raise HTTPException(status_code=403, detail="Access denied")

    # Groups and notes: only owner can delete
    if not is_owner and source.owner_id is not None:
        raise HTTPException(status_code=403, detail="Only the owner can delete this source")

    if source.type != "group":
        delete_vectors_by_source(source_id)
    await db.delete(source)
    await db.commit()
    return None


# --- Source Group endpoints ---


@router.get("/sources", response_model=list[SourceResponse])
async def list_sources(
    type: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List sources visible to the current user, optionally filtered by type."""
    sources = await get_visible_sources(user, type, db)

    responses = await _build_source_responses(sources, db, user.id)
    for s, resp in zip(sources, responses, strict=False):
        if s.type == "group":
            count_result = await db.execute(
                select(SourceMember).where(SourceMember.parent_id == s.id)
            )
            visible_count = 0
            for member in count_result.scalars().all():
                if await can_user_access_source(user.id, member.child_id, db):
                    visible_count += 1
            resp.member_count = visible_count
    return responses


@router.post(
    "/sources/groups",
    response_model=SourceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_group(
    body: CreateGroupRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new source group."""
    if body.project_id is not None:
        await _get_project_for_user(body.project_id, user.id, db)
    source = Source(type="group", name=body.name, owner_id=user.id)
    db.add(source)
    await db.flush()

    # Link to owner's workspace so it appears in source listings
    ws_link = WorkspaceSource(workspace_id=user.workspace.id, source_id=source.id)
    db.add(ws_link)
    if body.project_id is not None:
        asset = await materialize_source_asset(
            db=db,
            source=source,
            owner_id=user.id,
            origin_project_id=body.project_id,
            origin_session_id=None,
            visibility_scope="project",
            link_type="source",
        )
        await log_activity(
            db,
            project_id=body.project_id,
            actor_id=user.id,
            action="asset_uploaded",
            target_type="asset",
            target_id=asset.id,
            target_title=asset.title,
        )
    await db.commit()
    await db.refresh(source)
    resp = SourceResponse.model_validate(source)
    resp.member_count = 0
    resp.owner_id = user.id
    resp.can_edit = True
    return resp


@router.post(
    "/sources/upload",
    response_model=SourceResponse | ZipUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_source_global(
    file: UploadFile,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a file globally (not tied to any session). Supports PDF and ZIP files."""
    try:
        filename = file.filename or ""
        if filename.lower().endswith(".zip"):
            content = await file.read()
            return await _handle_zip_upload(content, db, owner_id=user.id)

        source, _needs_processing = await _create_source_pending(file, db, owner_id=user.id)
        duplicate_info = None
        if not _needs_processing:
            duplicate_info = await build_duplicate_upload_info(
                db=db,
                user=user,
                source=source,
            )
            if not duplicate_info.can_use_existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=duplicate_info.model_dump(),
                )
        await _ensure_workspace_link(user.workspace.id, source.id, db)
        await materialize_source_asset(
            db=db,
            source=source,
            owner_id=user.id,
            origin_project_id=None,
            origin_session_id=None,
            visibility_scope="private",
            link_type="source",
        )
        await db.commit()
        await db.refresh(source)
        response = SourceResponse.model_validate(source)
        response.duplicate_info = duplicate_info
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("File upload failed")
        raise HTTPException(status_code=500, detail=f"File processing failed: {e}")


@router.post("/sources/{source_id}/retry", response_model=SourceResponse)
async def retry_source(
    source_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reset a failed source back to pending so the worker re-processes it."""
    if not await can_user_access_source(user.id, source_id, db):
        raise HTTPException(status_code=404, detail="Source not found")
    result = await db.execute(select(Source).where(Source.id == source_id))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    if source.processing_state != "failed":
        raise HTTPException(status_code=400, detail="Only failed sources can be retried")
    source.processing_state = "pending"
    source.progress = 0
    source.error_message = None
    await db.commit()
    await db.refresh(source)
    return SourceResponse.model_validate(source)


@router.patch("/sources/{source_id}", response_model=SourceResponse)
async def update_source(
    source_id: str,
    body: UpdateSourceRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update source name (primarily for groups). Only the owner can rename."""
    result = await db.execute(select(Source).where(Source.id == source_id))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    if source.owner_id is not None and source.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Only the owner can rename this source")

    source.name = body.name
    await db.commit()
    await db.refresh(source)
    return SourceResponse.model_validate(source)


@router.get(
    "/sources/{source_id}/members", response_model=list[SourceMemberResponse]
)
async def list_group_members(
    source_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List direct members of a group."""
    result = await db.execute(select(Source).where(Source.id == source_id))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    if source.type != "group":
        raise HTTPException(status_code=400, detail="Source is not a group")
    # Editors (owner or readwrite share) can always manage membership, even
    # when the linked catalog asset is not published to the lab catalog.
    can_edit = await can_user_edit_source(user.id, source_id, db)
    if not can_edit and not await can_user_access_source(user.id, source_id, db):
        raise HTTPException(status_code=404, detail="Source not found")

    result = await db.execute(
        select(SourceMember)
        .where(SourceMember.parent_id == source_id)
        .order_by(SourceMember.added_at)
    )
    members = result.scalars().all()

    responses = []
    for m in members:
        if not can_edit and not await can_user_access_source(user.id, m.child_id, db):
            continue
        child_result = await db.execute(select(Source).where(Source.id == m.child_id))
        child_source = child_result.scalar_one_or_none()
        resp = SourceMemberResponse(
            id=m.id,
            parent_id=m.parent_id,
            child_id=m.child_id,
            added_at=m.added_at,
            child=SourceResponse.model_validate(child_source) if child_source else None,
        )
        responses.append(resp)
    return responses


@router.post(
    "/sources/{source_id}/members",
    response_model=SourceMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_group_member(
    source_id: str,
    body: AddMemberRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a member (source or group) to a group. Validates cycles and depth."""
    # Check permission: owner or readwrite
    if not await can_user_edit_source(user.id, source_id, db):
        raise HTTPException(status_code=403, detail="You don't have permission to modify this group")
    if not await can_user_access_source(user.id, body.child_id, db):
        # Editors may add sources they own/manage even when the linked
        # catalog asset is not published to the lab catalog.
        if not await can_user_edit_source(user.id, body.child_id, db):
            raise HTTPException(status_code=404, detail="Source not found")

    try:
        await validate_add_member(source_id, body.child_id, db)
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg:
            raise HTTPException(status_code=404, detail=error_msg)
        if "not a group" in error_msg:
            raise HTTPException(status_code=400, detail=error_msg)
        if "cycle" in error_msg:
            raise HTTPException(status_code=409, detail=error_msg)
        if "depth" in error_msg:
            raise HTTPException(status_code=400, detail=error_msg)
        raise HTTPException(status_code=400, detail=error_msg)

    # Check for duplicate membership
    result = await db.execute(
        select(SourceMember).where(
            SourceMember.parent_id == source_id,
            SourceMember.child_id == body.child_id,
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Member already exists in group")

    member = SourceMember(parent_id=source_id, child_id=body.child_id)
    db.add(member)

    child_result = await db.execute(
        select(Source).options(selectinload(Source.share)).where(Source.id == body.child_id)
    )
    child_source = child_result.scalar_one_or_none()

    await db.commit()
    await db.refresh(member)

    return SourceMemberResponse(
        id=member.id,
        parent_id=member.parent_id,
        child_id=member.child_id,
        added_at=member.added_at,
        child=SourceResponse.model_validate(child_source) if child_source else None,
    )


@router.delete(
    "/sources/{source_id}/members/{child_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_group_member(
    source_id: str,
    child_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a member from a group."""
    if not await can_user_edit_source(user.id, source_id, db):
        raise HTTPException(status_code=403, detail="You don't have permission to modify this group")

    result = await db.execute(
        select(SourceMember).where(
            SourceMember.parent_id == source_id,
            SourceMember.child_id == child_id,
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found in group")

    await db.delete(member)
    await db.commit()
    return None


@router.get(
    "/sources/{source_id}/resolved-sources",
    response_model=list[SourceResponse],
)
async def get_resolved_sources(
    source_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Recursively resolve all leaf sources (non-group) in a group."""
    result = await db.execute(select(Source).where(Source.id == source_id))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    if source.type != "group":
        raise HTTPException(status_code=400, detail="Source is not a group")
    if not await can_user_access_source(user.id, source_id, db):
        raise HTTPException(status_code=404, detail="Source not found")

    leaf_ids = await resolve_leaf_sources({source_id}, db)
    if not leaf_ids:
        return []

    result = await db.execute(select(Source).where(Source.id.in_(leaf_ids)))
    visible_sources = []
    for source in result.scalars().all():
        if await can_user_access_source(user.id, source.id, db):
            visible_sources.append(source)
    return await _build_source_responses(visible_sources, db, user.id)


# --- Sharing endpoints ---


@router.get("/sources/{source_id}/share")
async def get_share_info(
    source_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get sharing info for a source."""
    if not await can_user_access_source(user.id, source_id, db):
        raise HTTPException(status_code=404, detail="Source not found")
    result = await db.execute(
        select(SourceShare)
        .options(selectinload(SourceShare.sharer))
        .where(SourceShare.source_id == source_id)
    )
    share = result.scalar_one_or_none()
    if not share:
        return None
    sharer_name = None
    if share.sharer:
        sharer_name = share.sharer.display_name or share.sharer.username
    return {
        "shared_by": share.shared_by,
        "shared_by_name": sharer_name,
        "scope": share.scope,
        "project_id": share.project_id,
        "permission": share.permission,
        "shared_at": share.shared_at,
    }


@router.post(
    "/sources/{source_id}/share",
    status_code=status.HTTP_201_CREATED,
)
async def share_source_endpoint(
    source_id: str,
    body: ShareSourceRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Share a source. Collections do not grant access to their child files."""
    try:
        share_record, auto_shared_count = await share_source(
            source_id, user, body.scope, body.project_id, body.permission, db,
        )
        source = await db.scalar(select(Source).where(Source.id == source_id))
        if source:
            await sync_source_share_to_asset(
                db=db,
                source=source,
                share=share_record,
                fallback_owner_id=user.id,
            )
        await db.commit()
        return {
            "shared": True,
            "auto_shared_files": auto_shared_count,
            "scope": share_record.scope,
            "permission": share_record.permission,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.delete(
    "/sources/{source_id}/share",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def unshare_source_endpoint(
    source_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Unshare a source. Files cannot be unshared."""
    try:
        await unshare_source(source_id, user, db)
        source = await db.scalar(select(Source).where(Source.id == source_id))
        if source:
            await sync_source_share_to_asset(
                db=db,
                source=source,
                share=None,
                fallback_owner_id=user.id,
            )
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return None


@router.patch("/sources/{source_id}/share")
async def update_share_endpoint(
    source_id: str,
    body: UpdateShareRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update share scope or permission for a source."""
    try:
        share_record = await update_share(
            source_id, user, body.scope, body.project_id, body.permission, db,
        )
        source = await db.scalar(select(Source).where(Source.id == source_id))
        if source:
            await sync_source_share_to_asset(
                db=db,
                source=source,
                share=share_record,
                fallback_owner_id=user.id,
            )
        await db.commit()
        return {
            "scope": share_record.scope,
            "project_id": share_record.project_id,
            "permission": share_record.permission,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get("/sources/{source_id}/share-preview")
async def preview_share(
    source_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Preview collection sharing side effects.

    Collections are organizational only, so sharing them never auto-shares files.
    """
    result = await db.execute(select(Source).where(Source.id == source_id))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    if source.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Only the owner can share")

    unshared_count = 0
    if source.type == "group":
        unshared_count = await count_unshared_group_files(source_id, db)
    return {"unshared_file_count": unshared_count}


# --- Private helpers ---


async def _restore_duplicate_upload(
    *,
    source: Source,
    content: bytes,
    filename: str,
    owner_id: str | None,
    db: AsyncSession,
) -> None:
    if owner_id != source.owner_id or owner_id is None:
        user = await db.get(User, owner_id) if owner_id else None
        duplicate_info = (
            await build_duplicate_upload_info(db=db, user=user, source=source)
            if user else None
        )
        if duplicate_info is None or not duplicate_info.can_use_existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=duplicate_info.model_dump() if duplicate_info else "Source access required",
            )

    try:
        file_exists = bool(source.content_path) and resolve_file_path(source.content_path).is_file()
    except ValueError:
        file_exists = False
    if not file_exists:
        stored_filename = Path(source.content_path).name if source.content_path else filename
        source.content_path = save_file(content, compute_file_hash(content), stored_filename)


async def _create_source_from_bytes(
    content: bytes,
    filename: str,
    db: AsyncSession,
    owner_id: str | None = None,
) -> tuple[Source, bool]:
    """Persist a pending Source row for background processing.

    Returns (source, needs_processing). needs_processing is True when a fresh
    row was created. The worker service will pick it up automatically after
    the transaction is committed.
    If the file's content_hash already matches an existing Source, that
    Source is returned with needs_processing=False.
    """
    if len(content) > settings.max_file_size_mb * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {settings.max_file_size_mb}MB size limit",
        )

    content_hash = compute_file_hash(content)

    result = await db.execute(
        select(Source).where(Source.content_hash == content_hash)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        await _restore_duplicate_upload(
            source=existing, content=content, filename=filename, owner_id=owner_id, db=db,
        )
        if existing.processing_state == "ready":
            # Already successfully processed — deduplicate
            return existing, False
        # Previous run failed or stalled — reset and re-process
        existing.processing_state = "pending"
        existing.progress = 0
        existing.error_message = None
        return existing, True

    file_path = save_file(content, content_hash, filename)

    source = Source(
        type="file",
        name=filename,
        content_hash=content_hash,
        content_path=file_path,
        processing_state="pending",
        progress=0,
        owner_id=owner_id,
    )
    db.add(source)
    await db.flush()
    return source, True


async def _create_source_pending(
    file: UploadFile,
    db: AsyncSession,
    owner_id: str | None = None,
) -> tuple[Source, bool]:
    """Thin wrapper around _create_source_from_bytes for UploadFile objects."""
    content = await file.read()
    filename = file.filename or "upload.pdf"
    return await _create_source_from_bytes(content, filename, db, owner_id=owner_id)


async def _create_data_package_source(
    content: bytes,
    filename: str,
    meta: dict,
    db: AsyncSession,
    owner_id: str | None = None,
) -> tuple[Source, bool]:
    """Persist a pending data-package Source row (ZIP stored as-is, not extracted).

    Same dedup-by-content_hash semantics as _create_source_from_bytes.
    The package is indexed from its meta info by the worker.
    """
    if len(content) > settings.max_file_size_mb * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {settings.max_file_size_mb}MB size limit",
        )

    content_hash = compute_file_hash(content)

    result = await db.execute(
        select(Source).where(Source.content_hash == content_hash)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        await _restore_duplicate_upload(
            source=existing, content=content, filename=filename, owner_id=owner_id, db=db,
        )
        if existing.processing_state == "ready":
            # Already successfully processed — deduplicate
            return existing, False
        # Previous run failed or stalled — reset and re-process
        existing.processing_state = "pending"
        existing.progress = 0
        existing.error_message = None
        return existing, True

    file_path = save_file(content, content_hash, filename)

    source = Source(
        type="data_package",
        name=meta.get("title") or filename,
        content_hash=content_hash,
        content_path=file_path,
        meta_info=meta,
        processing_state="pending",
        progress=0,
        owner_id=owner_id,
    )
    db.add(source)
    await db.flush()
    return source, True


async def _create_data_package_pending(
    file: UploadFile,
    meta_title: str | None,
    meta_description: str | None,
    meta_tags: str | None,
    db: AsyncSession,
    owner_id: str | None = None,
) -> tuple[Source, bool]:
    """Validate and persist a data-package upload (ZIP + user-supplied meta info)."""
    filename = file.filename or ""
    if not filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Data package upload must be a .zip file")
    title = (meta_title or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="meta_title is required for data package uploads")
    tags = [t.strip() for t in (meta_tags or "").split(",") if t.strip()]
    meta = {
        "title": title,
        "description": (meta_description or "").strip(),
        "tags": tags,
        "filename": filename,
    }
    content = await file.read()
    return await _create_data_package_source(content, filename, meta, db, owner_id=owner_id)


async def _handle_file_upload(
    file: UploadFile,
    session_id: str,
    workspace_id: str,
    db: AsyncSession,
    owner_id: str | None = None,
    upload_kind: str | None = None,
    meta_title: str | None = None,
    meta_description: str | None = None,
    meta_tags: str | None = None,
) -> SourceResponse:
    if upload_kind == "data_package":
        source, _needs_processing = await _create_data_package_pending(
            file, meta_title, meta_description, meta_tags, db, owner_id=owner_id
        )
    else:
        source, _needs_processing = await _create_source_pending(file, db, owner_id=owner_id)
    duplicate_info = None
    if not _needs_processing:
        user = await db.scalar(select(User).where(User.id == owner_id)) if owner_id else None
        if user is not None:
            duplicate_info = await build_duplicate_upload_info(
                db=db,
                user=user,
                source=source,
            )
            if not duplicate_info.can_use_existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=duplicate_info.model_dump(),
                )

    await _ensure_workspace_link(workspace_id, source.id, db)
    await _ensure_session_link(session_id, source.id, db)
    project_id = await _get_session_project_id(session_id, db)
    await materialize_source_asset(
        db=db,
        source=source,
        owner_id=owner_id,
        origin_project_id=project_id,
        origin_session_id=session_id,
        visibility_scope="project" if project_id else "private",
        link_type="source",
    )

    await db.commit()
    await db.refresh(source)
    response = SourceResponse.model_validate(source)
    response.duplicate_info = duplicate_info
    return response


async def _link_existing_source(
    source_id: str,
    session_id: str,
    workspace_id: str,
    db: AsyncSession,
) -> SourceResponse:
    result = await db.execute(select(Source).where(Source.id == source_id))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    await _ensure_workspace_link(workspace_id, source_id, db)
    await _ensure_session_link(session_id, source_id, db)
    project_id = await _get_session_project_id(session_id, db)
    await materialize_source_asset(
        db=db,
        source=source,
        owner_id=source.owner_id,
        origin_project_id=project_id,
        origin_session_id=session_id,
        visibility_scope="project" if project_id else "private",
        link_type="source",
    )

    await db.commit()
    return SourceResponse.model_validate(source)


async def _ensure_workspace_link(
    workspace_id: str, source_id: str, db: AsyncSession
) -> None:
    result = await db.execute(
        select(WorkspaceSource).where(
            WorkspaceSource.workspace_id == workspace_id,
            WorkspaceSource.source_id == source_id,
        )
    )
    if not result.scalar_one_or_none():
        db.add(WorkspaceSource(workspace_id=workspace_id, source_id=source_id))


async def _ensure_session_link(
    session_id: str, source_id: str, db: AsyncSession
) -> None:
    result = await db.execute(
        select(SessionSource).where(
            SessionSource.session_id == session_id,
            SessionSource.source_id == source_id,
        )
    )
    if not result.scalar_one_or_none():
        db.add(SessionSource(session_id=session_id, source_id=source_id))


async def _get_or_create_group(
    name: str, db: AsyncSession, owner_id: str | None = None
) -> tuple[Source, bool]:
    """Find an existing group by name (owned by the same user) or create a new one."""
    query = select(Source).where(Source.type == "group", Source.name == name)
    if owner_id:
        query = query.where(Source.owner_id == owner_id)
    result = await db.execute(query)
    existing = result.scalar_one_or_none()
    if existing:
        return existing, False
    group = Source(type="group", name=name, owner_id=owner_id)
    db.add(group)
    await db.flush()
    return group, True


async def _ensure_group_membership(
    parent_id: str, child_id: str, db: AsyncSession
) -> None:
    """Idempotently add a child source to a parent group."""
    result = await db.execute(
        select(SourceMember).where(
            SourceMember.parent_id == parent_id,
            SourceMember.child_id == child_id,
        )
    )
    if not result.scalar_one_or_none():
        db.add(SourceMember(parent_id=parent_id, child_id=child_id))


async def _handle_zip_upload(
    content: bytes,
    db: AsyncSession,
    session_id: str | None = None,
    workspace_id: str | None = None,
    owner_id: str | None = None,
    project_id: str | None = None,
) -> ZipUploadResponse:
    """Extract documents from a ZIP, create sources and groups, start processing."""
    try:
        documents, errors = extract_documents_from_zip(content, settings.max_file_size_mb)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not documents and not errors:
        raise HTTPException(status_code=400, detail="ZIP contains no supported document files")

    sources: list[Source] = []
    needs_processing: list[tuple[str, str]] = []  # (source_id, content_path)
    groups: list[Source] = []
    created_source_ids: list[str] = []
    seen_group_names: dict[str, Source] = {}

    for document in documents:
        source, is_new = await _create_source_from_bytes(
            document.content, document.filename, db, owner_id=owner_id
        )
        sources.append(source)
        if is_new:
            created_source_ids.append(source.id)
            needs_processing.append((source.id, source.content_path))
            logger.info("ZIP: created new source %s (%s)", source.id, document.filename)
        else:
            logger.info("ZIP: deduped source %s (%s)", source.id, document.filename)

        if workspace_id:
            await _ensure_workspace_link(workspace_id, source.id, db)
        if session_id:
            await _ensure_session_link(session_id, source.id, db)
        resolved_project_id = project_id or await _get_session_project_id(session_id, db)
        await materialize_source_asset(
            db=db,
            source=source,
            owner_id=owner_id,
            origin_project_id=resolved_project_id,
            origin_session_id=session_id,
            visibility_scope="project" if resolved_project_id else "private",
            link_type="source",
        )

        # Create groups for each directory component and add membership
        for dir_name in document.dir_parts:
            if dir_name in seen_group_names:
                group = seen_group_names[dir_name]
            else:
                group, group_is_new = await _get_or_create_group(
                    dir_name,
                    db,
                    owner_id=owner_id,
                )
                if group_is_new:
                    created_source_ids.append(group.id)
                seen_group_names[dir_name] = group
                groups.append(group)
                if workspace_id:
                    await _ensure_workspace_link(workspace_id, group.id, db)
                await materialize_source_asset(
                    db=db,
                    source=group,
                    owner_id=owner_id,
                    origin_project_id=resolved_project_id,
                    origin_session_id=session_id,
                    visibility_scope="project" if resolved_project_id else "private",
                    link_type="source",
                )
            await _ensure_group_membership(group.id, source.id, db)

    await db.commit()

    # Refresh all sources to get generated fields
    for source in sources:
        await db.refresh(source)
    for group in groups:
        await db.refresh(group)

    # Worker will pick up pending sources automatically via polling

    return ZipUploadResponse(
        sources=await _build_source_responses(sources, db),
        groups=await _build_source_responses(groups, db),
        errors=errors,
        created_source_ids=created_source_ids,
    )
