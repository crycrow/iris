from app.core.clock import today as app_today
from datetime import date, timedelta
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.common.models import User, Project
from app.common.permissions import (
    get_current_user,
    ensure_project_access,
    accessible_project_ids,
)
from app.common.services.access_log import audit
from app.modules.time_tracking.models import Task, TimeEntry, TaskAssignment, Calendar
from app.modules.time_tracking.schemas import EntryCreate, Result, Items
from app.modules.time_tracking.services.timesheet import validate_entry
from .tasks import get_task

router = APIRouter(tags=["Табель"])


def task_depths(db: Session, project_ids: set[int]) -> dict[int, int]:
    parents = dict(db.execute(select(Task.task_id, Task.parent_task_id)
                              .where(Task.project_id.in_(project_ids))).all())
    depths = {}
    for task_id, parent_id in parents.items():
        seen, depth = {task_id}, 0
        while parent_id in parents and parent_id not in seen:
            seen.add(parent_id)
            depth += 1
            parent_id = parents[parent_id]
        depths[task_id] = depth
    return depths


@router.get("/api/time-entries")
def list_entries(
    project_id: int | None = None,
    user_id: int | None = None,
    from_date: date | None = Query(None, alias="from"),
    to_date: date | None = Query(None, alias="to"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    query = (
        select(TimeEntry, Task.name, Project.name, Task.project_id, User.full_name, Task.parent_task_id)
        .join(Task, Task.task_id == TimeEntry.task_id)
        .join(Project, Project.project_id == Task.project_id)
        .join(User, User.user_id == TimeEntry.user_id)
    )
    if project_id:
        ensure_project_access(db, user, project_id)
        query = query.where(Task.project_id == project_id)
    if user.role == "employee":
        if user_id is not None and user_id != user.user_id:
            raise HTTPException(403, "Доступны только собственные списания")
        query = query.where(TimeEntry.user_id == user.user_id)
    elif user.role == "manager":
        query = query.where(Project.manager_id == user.user_id)
    if user_id:
        query = query.where(TimeEntry.user_id == user_id)
    if from_date:
        query = query.where(TimeEntry.work_date >= from_date)
    if to_date:
        query = query.where(TimeEntry.work_date <= to_date)
    rows = list(db.execute(query.order_by(TimeEntry.work_date.desc(), TimeEntry.entry_id.desc())))
    depths = task_depths(db, {row[3] for row in rows})
    items = [
        {
            **{c.name: getattr(entry, c.name) for c in TimeEntry.__table__.columns},
            "task_name": task,
            "project_name": project,
            "project_id": pid,
            "user_name": full_name,
            "parent_task_id": parent_id,
            "task_depth": depths.get(entry.task_id, 0),
        }
        for entry, task, project, pid, full_name, parent_id in rows
    ]
    audit(
        user.user_id,
        "read",
        "time_entries.users",
        sorted({row["user_id"] for row in items}),
    )
    return {"items": items, "total": sum(float(row["hours"]) for row in items)}


@router.post("/api/time-entries", response_model=dict[str, int], status_code=201)
def create_entry(
    body: EntryCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    get_task(db, user, body.task_id)
    task = validate_entry(db, user.user_id, body.task_id, body.work_date, body.hours)
    ensure_project_access(db, user, task.project_id)
    entry = TimeEntry(user_id=user.user_id, **body.model_dump())
    db.add(entry)
    db.commit()
    return {"entry_id": entry.entry_id}


@router.put("/api/time-entries/{entry_id}", response_model=Result)
def update_entry(
    entry_id: int,
    body: EntryCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    entry = db.get(TimeEntry, entry_id)
    if entry is None:
        raise HTTPException(404, "Запись не найдена")
    if entry.user_id != user.user_id:
        raise HTTPException(403, "Изменять можно только собственные списания")
    get_task(db, user, entry.task_id)
    get_task(db, user, body.task_id)
    task = validate_entry(
        db, user.user_id, body.task_id, body.work_date, body.hours, entry_id
    )
    ensure_project_access(db, user, task.project_id)
    for key, value in body.model_dump().items():
        setattr(entry, key, value)
    db.commit()
    return {"ok": True}


@router.delete("/api/time-entries/{entry_id}", response_model=Result)
def delete_entry(
    entry_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    entry = db.get(TimeEntry, entry_id)
    if entry is None:
        raise HTTPException(404, "Запись не найдена")
    if entry.user_id != user.user_id:
        raise HTTPException(403, "Удалять можно только собственные списания")
    get_task(db, user, entry.task_id)
    db.delete(entry)
    db.commit()
    return {"ok": True}


@router.get("/api/my/entry-tasks", response_model=Items)
def entry_tasks(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    parents = select(Task.parent_task_id).where(Task.parent_task_id.is_not(None))
    rows = list(db.execute(
        select(Task, Project)
        .join(Project, Project.project_id == Task.project_id)
        .join(TaskAssignment, TaskAssignment.task_id == Task.task_id)
        .where(
            TaskAssignment.user_id == user.user_id,
            Task.project_id.in_(accessible_project_ids(db, user)),
            Task.status.not_in(("done", "cancelled")),
            Task.is_milestone.is_(False),
            Task.task_id.not_in(parents),
            Project.status.in_(("planned", "active")),
        )
    ))
    depths = task_depths(db, {project.project_id for task, project in rows})
    projects: dict[int, dict[str, Any]] = {}
    for task, project in rows:
        projects.setdefault(
            project.project_id,
            {
                "project_id": project.project_id,
                "project_name": project.name,
                "tasks": [],
            },
        )["tasks"].append(
            {"task_id": task.task_id, "name": task.name, "due_date": task.due_date,
             "parent_task_id": task.parent_task_id, "task_depth": depths.get(task.task_id, 0)}
        )
    return {"items": list(projects.values())}


@router.get("/api/my/summary")
def my_summary(
    from_date: date | None = Query(None, alias="from"),
    to_date: date | None = Query(None, alias="to"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    today = app_today()
    start = from_date or today - timedelta(days=today.weekday())
    end = to_date or start + timedelta(days=6)
    if start > end:
        raise HTTPException(422, "Начало периода должно быть не позже окончания")
    entries = list_entries(
        user_id=user.user_id, from_date=start, to_date=end, db=db, user=user
    )["items"]
    calendar = {
        day: float(hours)
        for day, hours in db.execute(
            select(Calendar.calendar_date, func.max(Calendar.working_hours))
            .where(
                Calendar.calendar_date >= start,
                Calendar.calendar_date <= end,
                Calendar.project_id.in_(accessible_project_ids(db, user)),
            )
            .group_by(Calendar.calendar_date)
        )
    }
    days: list[dict[str, Any]] = []
    while start <= end:
        hours = sum(float(e["hours"]) for e in entries if e["work_date"] == start)
        norm = float(calendar.get(start, 0 if start.weekday() > 4 else 8))
        days.append(
            {"date": start, "hours": hours, "weekend": norm == 0, "capacity": norm}
        )
        start += timedelta(days=1)
    return {
        "days": days,
        "total": sum(d["hours"] for d in days),
        "capacity": sum(d["capacity"] for d in days),
        "missing": sum(
            not d["hours"] and not d["weekend"] and d["date"] < today for d in days
        ),
    }
