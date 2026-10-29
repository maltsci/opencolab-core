import re
from datetime import UTC, datetime

import httpx
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.access_request import AccessRequest
from app.models.project import ResearcherProject
from app.models.research_asset import ProjectAssetLink, ResearchAsset
from app.models.research_direction import ResearchDirection
from app.models.research_direction_link import ResearchAssetDirection
from app.models.user import User
from app.schemas.research_asset import (
    LibraryCatalogSearchResult,
    LibraryFullTextSearchResult,
    LibrarySearchResponse,
)
from app.services.rag_service import _rag_chunks
from app.services.access_policy_service import AccessContext
from app.services.research_asset_service import (
    can_user_discover_asset,
    can_user_read_asset,
)

LIBRARY_SEMANTIC_MIN_SCORE = 0.60


def _contains_search_token(text: str, token: str) -> bool:
    if token.isascii() and token.isalnum() and len(token) <= 3:
        return re.search(
            rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])",
            text,
        ) is not None
    return token in text


def _matches_search_tokens(text: str, tokens: list[str]) -> bool:
    return all(_contains_search_token(text, token) for token in tokens)


def _list_metadata(metadata: dict, key: str) -> list[str]:
    value = metadata.get(key, [])
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if isinstance(item, (str, int, float))]
    return []


def _catalog_values(
    asset: ResearchAsset,
    *,
    steward_name: str | None,
    directions: list[dict],
) -> dict:
    metadata = asset.catalog_metadata_json or {}
    bibliographic = metadata.get("bibliographic")
    if not isinstance(bibliographic, dict):
        bibliographic = {}
    resource_profile = metadata.get("resource_profile")
    if not isinstance(resource_profile, dict):
        resource_profile = {}
    title = str(metadata.get("title") or asset.title)
    authors = _list_metadata(metadata, "authors") or _list_metadata(
        bibliographic, "authors"
    )
    tags = _list_metadata(metadata, "tags")
    keywords = _list_metadata(bibliographic, "keywords")
    metadata_steward_name = metadata.get("steward_name")
    project_name = metadata.get("project_name")
    date = metadata.get("date")
    purpose = resource_profile.get("purpose")
    return {
        "title": title,
        "asset_type": asset.asset_type,
        "description": asset.description
        or (purpose if isinstance(purpose, str) else None),
        "authors": authors,
        "tags": tags,
        "keywords": keywords,
        "directions": directions,
        "steward_name": steward_name
        or (
            metadata_steward_name
            if isinstance(metadata_steward_name, str)
            else None
        ),
        "project_name": project_name if isinstance(project_name, str) else None,
        "date": date if isinstance(date, str) else None,
    }


def _match_type(values: dict, query: str) -> str | None:
    normalized_query = query.casefold().strip()
    if not normalized_query:
        return "catalog"
    tokens = normalized_query.split()
    title = values["title"].casefold()
    if _matches_search_tokens(title, tokens):
        return "title"
    keywords = " ".join(values["keywords"]).casefold()
    if keywords and _matches_search_tokens(keywords, tokens):
        return "keyword"
    catalog = " ".join(
        [
            *values["authors"],
            *values["tags"],
            values["description"] or "",
            values["asset_type"],
            *[direction["name"] for direction in values["directions"]],
            values["steward_name"] or "",
            values["project_name"] or "",
            values["date"] or "",
        ]
    ).casefold()
    if _matches_search_tokens(catalog, tokens):
        return "catalog"
    return None


async def _active_request_status(
    db: AsyncSession,
    *,
    asset_id: str,
    requester_id: str,
) -> str | None:
    now = datetime.now(UTC)
    request = await db.scalar(
        select(AccessRequest.status)
        .where(
            AccessRequest.research_asset_id == asset_id,
            AccessRequest.requester_id == requester_id,
            AccessRequest.status.in_(["pending", "approved"]),
            (
                (AccessRequest.status == "pending")
                | (AccessRequest.grant_valid_until.is_(None))
                | (AccessRequest.grant_valid_until > now)
            ),
        )
        .order_by(AccessRequest.created_at.desc(), AccessRequest.id.desc())
    )
    return request


async def _search_assets(
    db: AsyncSession,
    *,
    user: User,
    query: str,
    limit: int,
    project_id: str | None,
    include_project_assets: bool = False,
) -> LibrarySearchResponse:
    stmt = select(ResearchAsset)
    if project_id is None:
        scope = ResearchAsset.visibility_scope.in_(["lab_private", "lab_public"])
        if include_project_assets:
            member_project_asset = (
                select(ProjectAssetLink.id)
                .join(
                    ResearcherProject,
                    ResearcherProject.project_id == ProjectAssetLink.project_id,
                )
                .where(
                    ProjectAssetLink.asset_id == ResearchAsset.id,
                    ResearcherProject.researcher_id == user.id,
                )
                .exists()
            )
            scope = or_(
                scope,
                (ResearchAsset.visibility_scope == "project") & member_project_asset,
            )
        stmt = stmt.where(scope)
    else:
        stmt = stmt.join(
            ProjectAssetLink, ProjectAssetLink.asset_id == ResearchAsset.id
        ).where(
            ProjectAssetLink.project_id == project_id,
        )
    assets = list(
        (
            await db.scalars(
                stmt.where(
                    ResearchAsset.publication_status == "active",
                    ResearchAsset.deleted_at.is_(None),
                )
                .order_by(ResearchAsset.updated_at.desc(), ResearchAsset.id.desc())
                .limit(limit)
            )
        ).all()
    )

    steward_ids = {asset.steward_user_id for asset in assets if asset.steward_user_id}
    steward_names: dict[str, str] = {}
    if steward_ids:
        steward_rows = (
            await db.execute(
                select(User.id, User.display_name, User.username).where(
                    User.id.in_(steward_ids)
                )
            )
        ).all()
        steward_names = {
            user_id: display_name or username
            for user_id, display_name, username in steward_rows
        }

    asset_directions: dict[str, list[dict]] = {asset.id: [] for asset in assets}
    asset_ids = [asset.id for asset in assets]
    if asset_ids:
        direction_rows = (
            await db.execute(
                select(
                    ResearchAssetDirection.research_asset_id,
                    ResearchDirection.id,
                    ResearchDirection.name,
                    ResearchDirection.status,
                )
                .join(
                    ResearchDirection,
                    ResearchDirection.id == ResearchAssetDirection.direction_id,
                )
                .where(ResearchAssetDirection.research_asset_id.in_(asset_ids))
                .order_by(
                    ResearchDirection.normalized_name,
                    ResearchDirection.id,
                )
            )
        ).all()
        for asset_id, direction_id, direction_name, direction_status in direction_rows:
            asset_directions[asset_id].append(
                {
                    "id": direction_id,
                    "name": direction_name,
                    "status": direction_status,
                }
            )

    catalog_results: list[LibraryCatalogSearchResult] = []
    content_candidates: dict[str, tuple[ResearchAsset, dict, str | None]] = {}
    content_context = (
        AccessContext(project_id=project_id, purpose="Search project asset content")
        if project_id is not None
        else None
    )
    for asset in assets:
        if not await can_user_discover_asset(db, user, asset):
            continue
        values = _catalog_values(
            asset,
            steward_name=steward_names.get(asset.steward_user_id or ""),
            directions=asset_directions[asset.id],
        )
        can_preview = await can_user_read_asset(
            db,
            user,
            asset,
            context=content_context,
        )
        searchable_values = values if can_preview else {**values, "keywords": []}
        request_status = await _active_request_status(
            db,
            asset_id=asset.id,
            requester_id=user.id,
        )
        match_type = _match_type(searchable_values, query)
        if match_type is not None:
            catalog_results.append(
                LibraryCatalogSearchResult(
                    id=asset.id,
                    **searchable_values,
                    match_type=match_type,
                    can_read_content=can_preview,
                    can_request_access=(
                        asset.visibility_scope == "lab_private"
                        and request_status is None
                        and not can_preview
                    ),
                    active_access_request_status=request_status,
                )
            )
            continue
        if can_preview and asset.source_id:
            content_candidates[asset.source_id] = (
                asset,
                searchable_values,
                request_status,
            )
            continue

    match_priority = {"title": 0, "keyword": 1, "catalog": 2}
    catalog_results.sort(key=lambda result: match_priority[result.match_type])
    catalog_results = catalog_results[:limit]

    remaining = limit - len(catalog_results)
    if not content_candidates or remaining <= 0:
        return LibrarySearchResponse(catalog_results=catalog_results)

    try:
        chunks = await _rag_chunks(
            query,
            list(content_candidates),
            db,
            remaining,
        )
    except httpx.HTTPError:
        return LibrarySearchResponse(
            catalog_results=catalog_results,
            full_text_search_available=False,
        )

    full_text_results: list[LibraryFullTextSearchResult] = []
    seen_asset_ids: set[str] = set()
    for chunk in chunks:
        try:
            score = float(chunk.get("score", 0))
        except (TypeError, ValueError):
            continue
        if score < LIBRARY_SEMANTIC_MIN_SCORE:
            continue
        source_id = chunk.get("source_id")
        candidate = content_candidates.get(source_id)
        if candidate is None:
            continue
        asset, values, request_status = candidate
        if asset.id in seen_asset_ids or not await can_user_read_asset(
            db,
            user,
            asset,
            context=content_context,
        ):
            continue
        snippet = str(chunk.get("text") or "").strip()
        if not snippet:
            continue
        full_text_results.append(
            LibraryFullTextSearchResult(
                id=asset.id,
                **values,
                match_type="semantic",
                can_read_content=True,
                can_request_access=False,
                active_access_request_status=request_status,
                snippet=snippet[:1000],
            )
        )
        seen_asset_ids.add(asset.id)

    return LibrarySearchResponse(
        full_text_results=full_text_results,
        catalog_results=catalog_results,
    )


async def search_library_assets(
    db: AsyncSession,
    *,
    user: User,
    query: str,
    limit: int,
    include_project_assets: bool = False,
) -> LibrarySearchResponse:
    return await _search_assets(
        db,
        user=user,
        query=query,
        limit=limit,
        project_id=None,
        include_project_assets=include_project_assets,
    )


async def search_project_assets(
    db: AsyncSession,
    *,
    user: User,
    project_id: str,
    query: str,
    limit: int,
) -> LibrarySearchResponse:
    return await _search_assets(
        db,
        user=user,
        query=query,
        limit=limit,
        project_id=project_id,
    )
