import math

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user
from app.core.config import settings
from app.core.database import get_db
from app.models.notification import Notification
from app.models.user import User
from app.schemas.common import MessageResponse, PaginatedResponse
from app.schemas.notification import NotificationResponse

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get(
    "",
    response_model=PaginatedResponse[NotificationResponse],
    status_code=status.HTTP_200_OK,
    summary="List user notifications",
)
async def list_notifications(
    is_read: bool | None = Query(default=None, description="Filter by read status"),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(
        default=settings.DEFAULT_PAGE_SIZE,
        ge=1,
        le=settings.MAX_PAGE_SIZE,
        description="Items per page",
    ),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[NotificationResponse]:
    """Retrieve simulated notifications received by the current user."""
    offset = (page - 1) * page_size
    conditions = [Notification.user_id == current_user.id]

    if is_read is not None:
        conditions.append(Notification.is_read == is_read)

    # Count total
    count_stmt = select(func.count(Notification.id)).where(*conditions)
    total_res = await db.execute(count_stmt)
    total = total_res.scalar_one()

    # Query items
    stmt = (
        select(Notification)
        .where(*conditions)
        .order_by(Notification.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    notifications = list(result.scalars().all())

    total_pages = math.ceil(total / page_size) if total > 0 else 0

    return PaginatedResponse[NotificationResponse](
        items=[NotificationResponse.model_validate(n) for n in notifications],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1,
    )


@router.patch(
    "/{notification_id}/read",
    response_model=NotificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Mark notification as read",
)
async def mark_notification_read(
    notification_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationResponse:
    """Mark a specific notification as read."""
    stmt = select(Notification).where(
        Notification.id == notification_id,
        Notification.user_id == current_user.id,
    )
    result = await db.execute(stmt)
    notification = result.scalars().first()

    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notification with id {notification_id} not found.",
        )

    notification.is_read = True
    await db.flush()
    await db.refresh(notification)

    return NotificationResponse.model_validate(notification)


@router.post(
    "/read-all",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Mark all notifications as read",
)
async def mark_all_notifications_read(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Mark all unread notifications as read for current user."""
    stmt = select(Notification).where(
        Notification.user_id == current_user.id,
        Notification.is_read.is_(False),
    )
    result = await db.execute(stmt)
    unread = result.scalars().all()

    for n in unread:
        n.is_read = True

    await db.flush()
    return MessageResponse(
        message=f"Marked {len(unread)} notifications as read.",
    )
