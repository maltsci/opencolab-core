from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.source import Source, SourceMember

MAX_NESTING_DEPTH = 5


async def check_is_group(source_id: str, db: AsyncSession) -> Source:
    """Return the source if it exists and is type=group, else raise ValueError."""
    result = await db.execute(select(Source).where(Source.id == source_id))
    source = result.scalar_one_or_none()
    if source is None:
        raise ValueError(f"Source {source_id} not found")
    if source.type != "group":
        raise ValueError(f"Source {source_id} is not a group (type={source.type})")
    return source


async def would_create_cycle(
    parent_id: str, child_id: str, db: AsyncSession
) -> bool:
    """Check if adding child_id under parent_id would create a cycle.

    Walks up the ancestor chain from parent_id. If child_id appears
    as an ancestor, adding it as a child would form a cycle.
    """
    if parent_id == child_id:
        return True

    query = text("""
        WITH RECURSIVE ancestors AS (
            SELECT parent_id FROM source_members
            WHERE child_id = :parent_id
            UNION ALL
            SELECT sm.parent_id FROM source_members sm
            JOIN ancestors a ON sm.child_id = a.parent_id
        )
        SELECT 1 FROM ancestors WHERE parent_id = :child_id LIMIT 1
    """)
    result = await db.execute(query, {"parent_id": parent_id, "child_id": child_id})
    return result.scalar_one_or_none() is not None


async def get_nesting_depth(source_id: str, db: AsyncSession) -> int:
    """Get the current depth of a source in the group hierarchy.

    Returns 0 for a source with no parents, 1 for a direct child of a group, etc.
    """
    query = text("""
        WITH RECURSIVE depth_chain AS (
            SELECT parent_id, 1 AS depth FROM source_members
            WHERE child_id = :source_id
            UNION ALL
            SELECT sm.parent_id, dc.depth + 1 FROM source_members sm
            JOIN depth_chain dc ON sm.child_id = dc.parent_id
        )
        SELECT COALESCE(MAX(depth), 0) FROM depth_chain
    """)
    result = await db.execute(query, {"source_id": source_id})
    return result.scalar_one()


async def get_max_depth_below(source_id: str, db: AsyncSession) -> int:
    """Get the maximum depth below a source (how deep its subtree goes).

    Returns 0 for a leaf or empty group.
    """
    query = text("""
        WITH RECURSIVE depth_chain AS (
            SELECT child_id, 1 AS depth FROM source_members
            WHERE parent_id = :source_id
            UNION ALL
            SELECT sm.child_id, dc.depth + 1 FROM source_members sm
            JOIN depth_chain dc ON sm.parent_id = dc.child_id
        )
        SELECT COALESCE(MAX(depth), 0) FROM depth_chain
    """)
    result = await db.execute(query, {"source_id": source_id})
    return result.scalar_one()


async def validate_add_member(
    parent_id: str, child_id: str, db: AsyncSession
) -> None:
    """Validate that a member can be added to a group.

    Checks: parent is a group, no cycle, depth limit not exceeded.
    Raises ValueError with descriptive message on failure.
    """
    await check_is_group(parent_id, db)

    # Check child exists
    result = await db.execute(select(Source).where(Source.id == child_id))
    child = result.scalar_one_or_none()
    if child is None:
        raise ValueError(f"Source {child_id} not found")

    # Check for cycles
    if await would_create_cycle(parent_id, child_id, db):
        raise ValueError("Adding this member would create a cycle")

    # Check depth limit: depth_above(parent) + 1 + depth_below(child) <= MAX
    if child.type == "group":
        depth_above = await get_nesting_depth(parent_id, db)
        depth_below = await get_max_depth_below(child_id, db)
        total_depth = depth_above + 1 + depth_below
        if total_depth > MAX_NESTING_DEPTH:
            raise ValueError(
                f"Adding this group would exceed maximum nesting depth of {MAX_NESTING_DEPTH}"
            )


async def resolve_leaf_sources(
    group_ids: set[str], db: AsyncSession
) -> set[str]:
    """Recursively resolve all leaf source IDs (non-group) from a set of group IDs.

    Used before RAG retrieval to expand groups into searchable sources.
    """
    if not group_ids:
        return set()

    # Build placeholders for the seed IDs (compatible with both PostgreSQL and SQLite)
    ids_list = list(group_ids)
    placeholders = ", ".join(f":gid_{i}" for i in range(len(ids_list)))
    params = {f"gid_{i}": gid for i, gid in enumerate(ids_list)}

    query = text(f"""
        WITH RECURSIVE tree(id) AS (
            SELECT s.id FROM sources s WHERE s.id IN ({placeholders})
            UNION ALL
            SELECT sm.child_id
            FROM source_members sm
            JOIN tree t ON sm.parent_id = t.id
        )
        SELECT DISTINCT t.id FROM tree t
        JOIN sources s ON s.id = t.id
        WHERE s.type != 'group'
    """)
    result = await db.execute(query, params)
    return {row[0] for row in result.fetchall()}


async def get_group_ids_from_sources(
    source_ids: set[str], db: AsyncSession
) -> set[str]:
    """Filter a set of source IDs to return only those with type='group'."""
    if not source_ids:
        return set()

    result = await db.execute(
        select(Source.id).where(Source.id.in_(source_ids), Source.type == "group")
    )
    return {row[0] for row in result.fetchall()}


async def expand_source_ids_for_rag(
    source_ids: list[str], db: AsyncSession, user_id: str | None = None
) -> list[str]:
    """Expand a list of source IDs by resolving any groups to their leaf sources.

    Returns a deduplicated list of non-group source IDs ready for RAG retrieval.
    When user_id is provided, only sources visible to that user are returned.
    """
    all_ids = set(source_ids)
    group_ids = await get_group_ids_from_sources(all_ids, db)

    if not group_ids:
        expanded = all_ids
    else:
        leaf_ids = await resolve_leaf_sources(group_ids, db)
        expanded = (all_ids - group_ids) | leaf_ids

    if user_id is None:
        return list(expanded)

    from app.services.sharing_service import can_user_access_source

    visible_ids = []
    for source_id in expanded:
        if await can_user_access_source(user_id, source_id, db):
            visible_ids.append(source_id)
    return visible_ids
