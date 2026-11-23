from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.core.database import get_db
from app.common.models import User
from app.common.permissions import get_current_user, ensure_project_access
from app.modules.time_tracking.models import (
    Task,
    Release,
    TaskActivity,
    TaskAssignment,
    TimeEntry,
)
from app.modules.time_tracking.schemas import (
    TaskCreate,
    TaskUpdate,
    CommentCreate,
    Items,
    TaskResult,
    Result,
)
from app.modules.time_tracking.services.task_view import task_rows, plan_tree

router = APIRouter(tags=["Задачи и календарный план"])


def get_task(db: Session, user: User, task_id: int, write: bool = False) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(404, "Задача не найдена")
    ensure_project_access(db, user, task.project_id, write=write)
    return task


def validate_task(db: Session, task: Task) -> None:
    if task.due_date < task.start_date:
        raise HTTPException(422, "Окончание не может быть раньше начала")
    if task.is_milestone and task.start_date != task.due_date:
        raise HTTPException(422, "Веха должна иметь одну дату")
    if task.parent_task_id:
        parent = db.get(Task, task.parent_task_id)
        if (
            parent is None
            or parent.project_id != task.project_id
            or parent.is_milestone
        ):
            raise HTTPException(
                422, "Родительская задача должна принадлежать проекту и не быть вехой"
            )
        if db.scalar(
            select(TaskAssignment.assignment_id)
            .where(TaskAssignment.task_id == parent.task_id)
            .limit(1)
        ) or db.scalar(
            select(TimeEntry.entry_id)
            .where(TimeEntry.task_id == parent.task_id)
            .limit(1)
        ):
            raise HTTPException(
                409,
                "У родительской задачи есть назначения или списания. Перенесите работы в подзадачи",
            )
        seen = {task.task_id}
        while parent:
            if parent.task_id in seen:
                raise HTTPException(422, "Циклическая иерархия задач запрещена")
            seen.add(parent.task_id)
            parent = (
                db.get(Task, parent.parent_task_id) if parent.parent_task_id else None
            )
    if task.release_id:
        release = db.get(Release, task.release_id)
        if release is None or release.project_id != task.project_id:
            raise HTTPException(422, "Релиз должен принадлежать проекту")
    if (
        task.is_milestone
        and task.task_id
        and db.scalar(
            select(TaskAssignment.assignment_id)
            .where(TaskAssignment.task_id == task.task_id)
            .limit(1)
        )
    ):
        raise HTTPException(409, "Задачу с назначениями нельзя превратить в веху")
    task.progress_pct = (
        100
        if task.status == "done"
        else 0 if task.status in ("backlog", "todo") else task.progress_pct
    )


@router.get("/api/projects/{project_id}/tasks", response_model=Items)
def list_tasks(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    ensure_project_access(db, user, project_id)
    return {
        "items": task_rows(
            db,
            list(
                db.scalars(
                    select(Task)
                    .where(Task.project_id == project_id)
                    .order_by(Task.start_date, Task.task_id)
                )
            ),
        )
    }


@router.get("/api/projects/{project_id}/plan", response_model=Items)
def get_plan(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return {"items": plan_tree(list_tasks(project_id, db, user)["items"])}


@router.post(
    "/api/projects/{project_id}/tasks", response_model=dict[str, int], status_code=201
)
def create_task(
    project_id: int,
    body: TaskCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    ensure_project_access(db, user, project_id, write=True)
    task = Task(project_id=project_id, **body.model_dump())
    validate_task(db, task)
    db.add(task)
    db.flush()
    db.add(
        TaskActivity(
            task_id=task.task_id,
            user_id=user.user_id,
            change_type="created",
            new_value=task.name,
        )
    )
    db.commit()
    return {"task_id": task.task_id}


@router.get("/api/tasks/{task_id}", response_model=TaskResult)
def task_detail(
    task_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    task = get_task(db, user, task_id)
    row = task_rows(db, [task])[0]
    activity = [
        {c.name: getattr(a, c.name) for c in TaskActivity.__table__.columns}
        for a in db.scalars(
            select(TaskActivity)
            .where(TaskActivity.task_id == task_id)
            .order_by(TaskActivity.changed_at.desc())
        )
    ]
    return {"task": row, "assignments": row["assignments"], "activity": activity}


@router.put("/api/tasks/{task_id}", response_model=Result)
def update_task(
    task_id: int,
    body: TaskUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    task = get_task(db, user, task_id)
    changes = body.model_dump(exclude_unset=True)
    project = ensure_project_access(db, user, task.project_id)
    manager = user.role == "admin" or (
        user.role == "manager" and project.manager_id == user.user_id
    )
    if not manager:
        assigned = db.scalar(
            select(TaskAssignment.assignment_id).where(
                TaskAssignment.task_id == task_id,
                TaskAssignment.user_id == user.user_id,
            )
        )
        if not assigned or set(changes) - {"status"}:
            raise HTTPException(
                403, "Можно изменять только статус назначенной вам задачи"
            )
    for field, value in changes.items():
        if value is None and field not in ("parent_task_id", "release_id"):
            raise HTTPException(422, "Обязательное поле нельзя очистить")
    old = {key: getattr(task, key) for key in changes}
    old_progress = task.progress_pct
    with db.no_autoflush:
        for key, value in changes.items():
            setattr(task, key, value)
        validate_task(db, task)
        for key in changes:
            if old[key] != getattr(task, key):
                db.add(
                    TaskActivity(
                        task_id=task_id,
                        user_id=user.user_id,
                        change_type=key,
                        old_value=str(old[key]),
                        new_value=str(getattr(task, key)),
                    )
                )
        if old_progress != task.progress_pct and "progress_pct" not in changes:
            db.add(
                TaskActivity(
                    task_id=task_id,
                    user_id=user.user_id,
                    change_type="progress_pct",
                    old_value=str(old_progress),
                    new_value=str(task.progress_pct),
                )
            )
    db.commit()
    return {"ok": True}


@router.post("/api/tasks/{task_id}/comments", response_model=Result)
def comment(
    task_id: int,
    body: CommentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    get_task(db, user, task_id)
    db.add(
        TaskActivity(
            task_id=task_id,
            user_id=user.user_id,
            change_type="comment",
            new_value=body.text,
        )
    )
    db.commit()
    return {"ok": True}


@router.delete("/api/tasks/{task_id}", response_model=Result)
def remove_task(
    task_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    task = get_task(db, user, task_id, write=True)
    try:
        db.delete(task)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            409, "У задачи есть связанные записи. Используйте статус «Отклонена»"
        )
    return {"ok": True}
