import logging

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.source import Source

logger = logging.getLogger(__name__)

_TERMINAL_STATES = ("ready", "failed")


async def mark_stale_sources_failed(db: AsyncSession) -> int:
    """Flip any Source in a non-terminal processing_state to 'failed'.

    Called on app startup: in-process asyncio tasks do not survive a restart,
    so any row still marked pending/parsing/embedding is orphaned.
    Returns the number of rows updated.
    """
    result = await db.execute(
        select(Source.id).where(Source.processing_state.notin_(_TERMINAL_STATES))
    )
    stale_ids = [row[0] for row in result.all()]
    if not stale_ids:
        return 0

    await db.execute(
        update(Source)
        .where(Source.id.in_(stale_ids))
        .values(
            processing_state="failed",
            progress=0,
            error_message="Interrupted by server restart",
        )
    )
    await db.commit()
    logger.warning("Marked %d stale source(s) as failed on startup", len(stale_ids))
    return len(stale_ids)
