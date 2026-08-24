import logging
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.database import SyncSessionLocal
from app.models.notification import Notification, NotificationType
from app.models.project import Project
from app.models.task import Task, TaskStatus
from app.workers.celery_app import celery_app

logger = logging.getLogger("taskflow.worker")


@celery_app.task(name="app.workers.tasks.notify_task_reassigned", bind=True, max_retries=3)
def notify_task_reassigned(
    self,
    task_id: int,
    new_assignee_id: int,
    task_title: str,
    project_id: int,
    old_assignee_id: int | None = None,
) -> dict:
    """
    Background job triggered when a task is assigned or reassigned to a user.
    Creates a persistent notification record and simulates external delivery (logs).
    """
    logger.info(
        f"[Celery Worker] Processing task reassignment: task_id={task_id}, "
        f"old_assignee={old_assignee_id}, new_assignee={new_assignee_id}"
    )

    with SyncSessionLocal() as session:
        try:
            # Create notification record for the new assignee
            notification = Notification(
                user_id=new_assignee_id,
                task_id=task_id,
                type=NotificationType.TASK_REASSIGNED,
                title=f"Task Assigned: {task_title}",
                message=(
                    f"You have been assigned to task '{task_title}'."
                    if not old_assignee_id
                    else f"Task '{task_title}' was reassigned to you."
                ),
                is_read=False,
            )
            session.add(notification)
            session.commit()
            session.refresh(notification)

            # Simulated notification delivery (e.g. Email / Push / SMS)
            logger.info(
                f"[SIMULATED NOTIFICATION - REASSIGNMENT] "
                f"Delivered notification to User #{new_assignee_id} for Task '{task_title}' (Task ID: {task_id})"
            )

            return {
                "status": "success",
                "notification_id": notification.id,
                "user_id": new_assignee_id,
                "task_id": task_id,
            }
        except Exception as exc:
            session.rollback()
            logger.error(f"[Celery Worker] Error notifying task reassignment: {exc}", exc_info=True)
            raise self.retry(exc=exc, countdown=5) from exc


@celery_app.task(name="app.workers.tasks.check_overdue_tasks")
def check_overdue_tasks() -> dict:
    """
    Periodic background job (Celery Beat) that scans for overdue tasks.
    Triggers notification records when task due_date has passed and status is not done.
    """
    now = datetime.now(UTC)
    logger.info(f"[Celery Beat] Scanning for overdue tasks at {now.isoformat()}...")

    with SyncSessionLocal() as session:
        try:
            # Find tasks where due_date < now and status != DONE
            stmt = (
                select(Task)
                .join(Project, Task.project_id == Project.id)
                .where(
                    Task.due_date < now,
                    Task.status != TaskStatus.DONE,
                )
            )
            overdue_tasks = session.scalars(stmt).all()
            notifications_created = 0

            for task in overdue_tasks:
                # Recipient is the assignee if set, otherwise project owner
                project = session.get(Project, task.project_id)
                if not project:
                    continue

                recipient_id = task.assignee_id or project.owner_id

                # Check if an overdue notification was already sent for this task
                existing_notif = session.scalars(
                    select(Notification).where(
                        Notification.task_id == task.id,
                        Notification.type == NotificationType.TASK_OVERDUE,
                        Notification.user_id == recipient_id,
                    )
                ).first()

                if not existing_notif:
                    notification = Notification(
                        user_id=recipient_id,
                        task_id=task.id,
                        type=NotificationType.TASK_OVERDUE,
                        title=f"Task Overdue: {task.title}",
                        message=(
                            f"The task '{task.title}' was due on "
                            f"{task.due_date.strftime('%Y-%m-%d %H:%M UTC')} and is currently not marked done."
                        ),
                        is_read=False,
                    )
                    session.add(notification)
                    notifications_created += 1

                    # Simulated alert delivery
                    logger.warning(
                        f"[SIMULATED NOTIFICATION - OVERDUE ALERT] "
                        f"Task #{task.id} '{task.title}' is overdue! Notified recipient User #{recipient_id}."
                    )

            session.commit()
            logger.info(
                f"[Celery Beat] Completed scan. Found {len(overdue_tasks)} overdue tasks, created {notifications_created} notifications."
            )
            return {
                "status": "success",
                "overdue_tasks_count": len(overdue_tasks),
                "notifications_created": notifications_created,
            }
        except Exception as exc:
            session.rollback()
            logger.error(f"[Celery Beat] Error checking overdue tasks: {exc}", exc_info=True)
            return {"status": "error", "error": str(exc)}
