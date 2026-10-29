from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.notification import Notification
from app.models.user import User

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    access_request_id: str | None
    read_at: datetime | None
    created_at: datetime


class NotificationPage(BaseModel):
    items: list[NotificationResponse]
    unread_count: int
    next_cursor: str | None


@router.get("", response_model=NotificationPage)
async def list_notifications(
    cursor: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Notification).where(Notification.user_id == user.id)
    if cursor:
        anchor = await db.scalar(select(Notification).where(
            Notification.id == cursor, Notification.user_id == user.id,
        ))
        if anchor is None:
            raise HTTPException(status_code=404, detail="Notification not found")
        anchor_time = select(Notification.created_at).where(Notification.id == anchor.id).scalar_subquery()
        query = query.where(or_(
            Notification.created_at < anchor_time,
            and_(Notification.created_at == anchor_time, Notification.id < anchor.id),
        ))
    rows = list((await db.scalars(query.order_by(
        Notification.created_at.desc(), Notification.id.desc(),
    ).limit(limit + 1))).all())
    unread = await db.scalar(select(func.count()).select_from(Notification).where(
        Notification.user_id == user.id, Notification.read_at.is_(None),
    ))
    return NotificationPage(
        items=[NotificationResponse.model_validate(row) for row in rows[:limit]],
        unread_count=unread or 0,
        next_cursor=rows[limit - 1].id if len(rows) > limit else None,
    )


@router.post("/read-all", status_code=204)
async def read_all_notifications(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    await db.execute(update(Notification).where(
        Notification.user_id == user.id, Notification.read_at.is_(None),
    ).values(read_at=datetime.now(UTC)))
    await db.commit()


@router.post("/{notification_id}/read", status_code=204)
async def read_notification(
    notification_id: str,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    row = await db.scalar(select(Notification).where(
        Notification.id == notification_id, Notification.user_id == user.id,
    ))
    if row is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    if row.read_at is None:
        row.read_at = datetime.now(UTC)
        await db.commit()
