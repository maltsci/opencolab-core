from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_activity import ProjectActivity


async def log_activity(
    db: AsyncSession,
    *,
    project_id: str,
    actor_id: str | None,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    target_title: str | None = None,
) -> ProjectActivity:
    """Record a project activity entry.

    Only flushes; the caller is responsible for committing the transaction.
    """
    activity = ProjectActivity(
        project_id=project_id,
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        target_title=target_title,
    )
    db.add(activity)
    await db.flush()
    return activity
