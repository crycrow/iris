from app.core.clock import today as app_today
from datetime import date, timedelta
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.common.models import User, Project
from app.modules.time_tracking.models import Task, TaskAssignment, TimeEntry


def previous_week_status(db: Session, user: User, today: date) -> dict:

    end = today - timedelta(days=today.weekday() + 1)
    start = end - timedelta(days=6)
    hours = float(db.scalar(select(func.coalesce(func.sum(TimeEntry.hours), 0)).where(
        TimeEntry.user_id == user.user_id,
        TimeEntry.work_date >= start,
        TimeEntry.work_date <= end,
    )))
    expected = db.scalar(select(TaskAssignment.assignment_id).join(Task).where(
        TaskAssignment.user_id == user.user_id,
        Task.start_date <= end,
        Task.due_date >= start,
        Task.status != "cancelled",
        Task.is_milestone.is_(False),
    ).limit(1)) is not None
    if user.role in ("manager", "admin") and not expected:
        expected = db.scalar(select(Project.project_id).where(
            Project.manager_id == user.user_id,
            Project.start_date <= end,
            Project.end_date >= start,
            Project.status.not_in(("planned", "cancelled")),
        ).limit(1)) is not None
    return {"from": start, "to": end, "hours": hours,
            "missing": user.role in ("employee", "manager", "admin") and expected and hours == 0}


def validate_entry(
    db: Session,
    user_id: int,
    task_id: int,
    work_date: date,
    hours: Decimal,
    exclude_entry_id: int | None = None,
) -> Task:
    if work_date > app_today():
        raise HTTPException(422, "Нельзя списывать часы будущей датой")
    if not Decimal("0.5") <= hours <= 24:
        raise HTTPException(422, "Укажите от 0,5 до 24 часов")
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(404, "Задача не найдена")
    if (
        task.status in ("done", "cancelled")
        or task.is_milestone
        or db.scalar(
            select(Task.task_id).where(Task.parent_task_id == task_id).limit(1)
        )
    ):
        raise HTTPException(
            422, "Списание разрешено только по незавершённой задаче без подзадач"
        )
    if (
        db.scalar(
            select(TaskAssignment.assignment_id).where(
                TaskAssignment.task_id == task_id, TaskAssignment.user_id == user_id
            )
        )
        is None
    ):
        raise HTTPException(403, "Списание разрешено только по назначенным вам задачам")
    daily = select(func.coalesce(func.sum(TimeEntry.hours), 0)).where(
        TimeEntry.user_id == user_id, TimeEntry.work_date == work_date
    )
    if exclude_entry_id:
        daily = daily.where(TimeEntry.entry_id != exclude_entry_id)
    if Decimal(db.scalar(daily)) + hours > 24:
        raise HTTPException(422, "Сумма списаний за день не может превышать 24 часа")
    return task
