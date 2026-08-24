from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.notification import NotificationType


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    task_id: int | None
    type: NotificationType
    title: str
    message: str
    is_read: bool
    created_at: datetime
    updated_at: datetime
