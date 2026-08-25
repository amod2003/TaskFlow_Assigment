from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.core.logging import logger


class NotificationType(StrEnum):
    TASK_OVERDUE = "task_overdue"
    TASK_REASSIGNED = "task_reassigned"
    TASK_STATUS_CHANGED = "task_status_changed"


@dataclass
class NotificationMessage:
    user_id: int
    task_id: int
    type: NotificationType
    title: str
    message: str
    metadata: dict[str, Any] | None = None


class NotificationDelivery(ABC):
    """Abstract notification delivery interface.

    Implementations can simulate delivery (current), send emails (SendGrid),
    SMS (Twilio), push notifications (Firebase), or WebSocket events.
    """

    @abstractmethod
    def send(self, notification: NotificationMessage) -> bool:
        """Deliver notification to the recipient. Returns True if successful."""
        raise NotImplementedError


class SimulatedNotificationDelivery(NotificationDelivery):
    """Production-ready simulation: logs delivery and returns success.

    Swap this implementation for a real provider without changing business logic.
    """

    def send(self, notification: NotificationMessage) -> bool:
        logger.info(
            f"[NotificationDelivery] type={notification.type} "
            f"user_id={notification.user_id} task_id={notification.task_id} "
            f"title={notification.title!r}"
        )
        return True
