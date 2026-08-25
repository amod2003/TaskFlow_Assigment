import enum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class NotificationType(enum.StrEnum):
    TASK_OVERDUE = "task_overdue"
    TASK_REASSIGNED = "task_reassigned"
    TASK_STATUS_CHANGED = "task_status_changed"


class Notification(Base):
    __tablename__ = "notifications"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    type: Mapped[NotificationType] = mapped_column(
        Enum(NotificationType, name="notification_type_enum", native_enum=False),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="notifications")

    def __repr__(self) -> str:
        return f"<Notification id={self.id} user_id={self.user_id} type='{self.type}' is_read={self.is_read}>"
