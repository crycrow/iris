from app.core.clock import today as app_today

"""Назначения и ресурсный план используют один источник плановых часов."""
from datetime import date
from decimal import Decimal, ROUND_DOWN
from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.common.models import ProjectMember
from app.common.permissions import ensure_project_participant
from app.modules.time_tracking.models import (
    Task,
    TaskAssignment,
    ResourcePlan,
)


def months_between(start: date, end: date) -> list[date]:
    result = []
    current = start.replace(day=1)
    while current <= end:
        result.append(current)
        current = date(current.year + (current.month == 12), current.month % 12 + 1, 1)
    return result


def allocate_exact(total: Decimal, weights: list[Decimal]) -> list[Decimal]:

    if not weights or total < 0:
        raise ValueError("Невозможно распределить часы")
    if not sum(weights):
        weights = [Decimal(1)] * len(weights)
    denominator = sum(weights)
    parts = [
        (total * w / denominator).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        for w in weights
    ]
    remainder = int((total - sum(parts)) * 100)
    for i in range(remainder):
        parts[i % len(parts)] += Decimal("0.01")
    return parts


def ensure_leaf(db: Session, task: Task) -> None:
    if (
        task.is_milestone
        or task.status == "cancelled"
        or db.scalar(
            select(Task.task_id).where(Task.parent_task_id == task.task_id).limit(1)
        )
    ):
        raise HTTPException(
            422, "Назначать часы можно только действующей задаче без подзадач"
        )


def assign_task(
    db: Session,
    task: Task,
    user_id: int,
    total_hours: Decimal,
    months: list[date] | None = None,
    actor_role: str = "admin",
) -> TaskAssignment:
    ensure_leaf(db, task)
    ensure_project_participant(db, task.project_id, user_id)
    selected = months or months_between(task.start_date, task.due_date)
    allowed = months_between(task.start_date, task.due_date)
    if not selected or any(m not in allowed for m in selected):
        raise HTTPException(422, "Месяц назначения выходит за сроки задачи")
    if len(set(selected)) != len(selected):
        raise HTTPException(422, "Месяцы назначения не должны повторяться")
    if actor_role != "admin" and any(m < app_today().replace(day=1) for m in selected):
        raise HTTPException(403, "Прошедшие месяцы изменяет только администратор")
    assignment = db.scalar(
        select(TaskAssignment).where(
            TaskAssignment.task_id == task.task_id, TaskAssignment.user_id == user_id
        )
    )
    if assignment is None:
        assignment = TaskAssignment(task_id=task.task_id, user_id=user_id)
        db.add(assignment)
        db.flush()
    if db.get(ProjectMember, (task.project_id, user_id)) is None:
        db.add(ProjectMember(project_id=task.project_id, user_id=user_id))
    for month, hours in zip(
        selected, allocate_exact(total_hours, [Decimal(1)] * len(selected))
    ):
        row = db.get(ResourcePlan, (assignment.assignment_id, month))
        if row is None:
            db.add(
                ResourcePlan(
                    assignment_id=assignment.assignment_id,
                    plan_month=month,
                    planned_hours=hours,
                )
            )
        else:
            row.planned_hours = hours
    db.flush()
    return assignment


def redistribute_month(
    db: Session,
    project_id: int,
    user_id: int,
    month: date,
    total_hours: Decimal,
    actor_role: str,
) -> None:
    ensure_project_participant(db, project_id, user_id)
    if actor_role != "admin" and month < app_today().replace(day=1):
        raise HTTPException(403, "Прошедшие месяцы изменяет только администратор")
    pairs = list(
        db.execute(
            select(TaskAssignment, Task)
            .join(Task, Task.task_id == TaskAssignment.task_id)
            .where(
                Task.project_id == project_id,
                TaskAssignment.user_id == user_id,
                Task.status != "cancelled",
            )
        )
    )
    parents = set(
        db.scalars(
            select(Task.parent_task_id).where(
                Task.project_id == project_id, Task.parent_task_id.is_not(None)
            )
        )
    )
    targets = [
        a
        for a, t in pairs
        if t.task_id not in parents
        and not t.is_milestone
        and month in months_between(t.start_date, t.due_date)
    ]
    if not targets:
        raise HTTPException(422, "Сначала назначьте сотруднику задачи на этот месяц")
    rows = [db.get(ResourcePlan, (a.assignment_id, month)) for a in targets]
    amounts = allocate_exact(
        total_hours, [Decimal(r.planned_hours) if r else Decimal(0) for r in rows]
    )
    for assignment, row, hours in zip(targets, rows, amounts):
        if row:
            row.planned_hours = hours
        else:
            db.add(
                ResourcePlan(
                    assignment_id=assignment.assignment_id,
                    plan_month=month,
                    planned_hours=hours,
                )
            )
    db.flush()


def update_month_assignments(
    db: Session,
    project_id: int,
    user_id: int,
    month: date,
    items: list[tuple[int, Decimal]],
    remove_task_ids: list[int],
    actor_role: str,
) -> None:
    if actor_role != "admin" and month < app_today().replace(day=1):
        raise HTTPException(403, "Прошедшие месяцы изменяет только администратор")
    ensure_project_participant(db, project_id, user_id)
    if db.get(ProjectMember, (project_id, user_id)) is None:
        raise HTTPException(422, "Сотрудник не входит в команду проекта")
    item_ids = [task_id for task_id, _ in items]
    if len(item_ids) != len(set(item_ids)) or len(remove_task_ids) != len(
        set(remove_task_ids)
    ):
        raise HTTPException(422, "Задача не может повторяться в изменениях месяца")
    if set(item_ids) & set(remove_task_ids):
        raise HTTPException(422, "Нельзя одновременно сохранить и удалить план задачи")
    tasks: dict[int, Task] = {}
    for task_id in item_ids + remove_task_ids:
        task = db.get(Task, task_id)
        if task is None or task.project_id != project_id:
            raise HTTPException(422, "Задача не принадлежит проекту")
        tasks[task_id] = task
    for task_id, hours in items:
        ensure_leaf(db, tasks[task_id])
        if month not in months_between(
            tasks[task_id].start_date, tasks[task_id].due_date
        ):
            raise HTTPException(422, "Месяц назначения выходит за сроки задачи")
        if not hours.is_finite() or hours < 0 or hours > Decimal("9999.99"):
            raise HTTPException(422, "Укажите корректное количество плановых часов")
    for task_id in remove_task_ids:
        assignment = db.scalar(
            select(TaskAssignment).where(
                TaskAssignment.task_id == task_id, TaskAssignment.user_id == user_id
            )
        )
        if assignment is not None:
            plan = db.get(ResourcePlan, (assignment.assignment_id, month))
            if plan is not None:
                db.delete(plan)
    for task_id, hours in items:
        assign_task(db, tasks[task_id], user_id, hours, [month], actor_role)
    db.flush()
