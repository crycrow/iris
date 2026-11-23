from app.core.clock import today as app_today
from collections import defaultdict
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, delete, or_
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.common.models import User, ProjectMember
from app.common.permissions import get_current_user, ensure_project_access
from app.common.services.access_log import audit
from app.common.services.people import name_sort_key
from app.modules.time_tracking.models import (
    Task,
    TaskAssignment,
    ResourcePlan,
    TimeEntry,
    Calendar,
    TaskActivity,
)
from app.modules.time_tracking.schemas import (
    Assignments,
    PlanUpdates,
    Result,
    CalendarUpdate,
    MonthAssignments,
)
from app.modules.time_tracking.services.resource_plan import (
    assign_task,
    redistribute_month,
    months_between,
    update_month_assignments,
)
from app.modules.time_tracking.services.working_calendar import ensure_calendar

router = APIRouter(tags=["Ресурсный план"])


@router.get("/api/projects/{project_id}/resources")
def resource_plan(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    project = ensure_project_access(db, user, project_id, write=True)
    start = project.start_date.replace(day=1)
    end = project.end_date.replace(day=1)
    plans: dict[tuple[int, str], float] = defaultdict(float)
    assignment_plans: dict[tuple[int, str], float] = defaultdict(float)
    planned_months: set[tuple[int, str]] = set()
    for plan, assignment in db.execute(
        select(ResourcePlan, TaskAssignment)
        .join(
            TaskAssignment, TaskAssignment.assignment_id == ResourcePlan.assignment_id
        )
        .join(Task, Task.task_id == TaskAssignment.task_id)
        .where(Task.project_id == project_id, Task.status != "cancelled")
    ):
        plans[assignment.user_id, plan.plan_month.strftime("%Y-%m")] += float(
            plan.planned_hours
        )
        assignment_plans[
            assignment.assignment_id, plan.plan_month.strftime("%Y-%m")
        ] += float(plan.planned_hours)
        planned_months.add(
            (assignment.assignment_id, plan.plan_month.strftime("%Y-%m"))
        )
        start = min(start, plan.plan_month)
        end = max(end, plan.plan_month)
    facts: dict[tuple[int, str], float] = defaultdict(float)
    assignment_facts: dict[tuple[int, int, str], float] = defaultdict(float)
    for entry in db.scalars(
        select(TimeEntry)
        .join(Task, Task.task_id == TimeEntry.task_id)
        .where(Task.project_id == project_id)
    ):
        facts[entry.user_id, entry.work_date.strftime("%Y-%m")] += float(entry.hours)
        assignment_facts[
            entry.task_id, entry.user_id, entry.work_date.strftime("%Y-%m")
        ] += float(entry.hours)
        start = min(start, entry.work_date.replace(day=1))
        end = max(end, entry.work_date.replace(day=1))
    months = [m.strftime("%Y-%m") for m in months_between(start, end)]
    assignments: dict[int, list[dict]] = defaultdict(list)
    assigned_pairs: set[tuple[int, int]] = set()
    for assignment, task in db.execute(
        select(TaskAssignment, Task)
        .join(Task, Task.task_id == TaskAssignment.task_id)
        .where(Task.project_id == project_id)
        .order_by(Task.start_date, Task.task_id)
    ):
        assigned_pairs.add((task.task_id, assignment.user_id))
        assignments[assignment.user_id].append(
            {
                "assignment_id": assignment.assignment_id,
                "task_id": task.task_id,
                "task_name": task.name,
                "start_date": task.start_date,
                "due_date": task.due_date,
                "status": task.status,
                "months": [
                    {
                        "month": m,
                        "plan": assignment_plans[assignment.assignment_id, m],
                        "fact": assignment_facts[task.task_id, assignment.user_id, m],
                        "has_plan": (assignment.assignment_id, m) in planned_months,
                    }
                    for m in months
                ],
            }
        )
    for task_id, user_id in {
        (task_id, user_id) for task_id, user_id, _ in assignment_facts
    } - assigned_pairs:
        task = db.get(Task, task_id)
        if task is None:
            continue
        assignments[user_id].append(
            {
                "assignment_id": None,
                "task_id": task.task_id,
                "task_name": task.name,
                "start_date": task.start_date,
                "due_date": task.due_date,
                "status": task.status,
                "months": [
                    {
                        "month": m,
                        "plan": 0,
                        "fact": assignment_facts[task_id, user_id, m],
                        "has_plan": False,
                    }
                    for m in months
                ],
            }
        )
    member_ids = select(ProjectMember.user_id).where(
        ProjectMember.project_id == project_id
    )
    users = list(
        db.scalars(
            select(User)
            .where(
                or_(
                    User.user_id.in_(member_ids),
                    User.user_id.in_({user_id for user_id, _ in facts}),
                )
            )
            .order_by(User.full_name)
        )
    )
    users.sort(key=lambda row: name_sort_key(row.full_name, row.user_id))
    rows = [
        {
            "user_id": u.user_id,
            "full_name": u.full_name,
            "is_blocked": u.is_blocked,
            "is_member": db.get(ProjectMember, (project_id, u.user_id)) is not None,
            "assignments": assignments[u.user_id],
            "months": [
                {"month": m, "plan": plans[u.user_id, m], "fact": facts[u.user_id, m]}
                for m in months
            ],
        }
        for u in users
    ]
    audit(user.user_id, "read", "resource_plan.users", [u.user_id for u in users])
    return {"months": months, "rows": rows}


@router.put("/api/projects/{project_id}/resources/month", response_model=Result)
def save_month_assignments(
    project_id: int,
    body: MonthAssignments,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    ensure_project_access(db, user, project_id, write=True)
    update_month_assignments(
        db,
        project_id,
        body.user_id,
        date.fromisoformat(body.month + "-01"),
        [(item.task_id, item.planned_hours) for item in body.items],
        body.remove_task_ids,
        user.role,
    )
    db.commit()
    audit(user.user_id, "update", "resource_plan.users", [body.user_id])
    return {"ok": True}


@router.post("/api/projects/{project_id}/resources/assign", response_model=Result)
def assign(
    project_id: int,
    body: Assignments,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    ensure_project_access(db, user, project_id, write=True)
    months = (
        [date.fromisoformat(m + "-01") for m in body.months] if body.months else None
    )
    for item in body.items:
        task = db.get(Task, item.task_id)
        if task is None or task.project_id != project_id:
            raise HTTPException(422, "Задача не принадлежит проекту")
        assign_task(db, task, body.user_id, item.planned_hours, months, user.role)
    db.commit()
    return {"ok": True}


@router.put("/api/projects/{project_id}/resources/plan", response_model=Result)
def save_plan(
    project_id: int,
    body: PlanUpdates,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    ensure_project_access(db, user, project_id, write=True)
    for item in body.updates:
        redistribute_month(
            db,
            project_id,
            item.user_id,
            date.fromisoformat(item.month + "-01"),
            item.planned_hours,
            user.role,
        )
    db.commit()
    return {"ok": True}


@router.delete("/api/task-assignments/{assignment_id}", response_model=Result)
def remove_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    assignment = db.get(TaskAssignment, assignment_id)
    if assignment is None:
        raise HTTPException(404, "Назначение не найдено")
    task = db.get(Task, assignment.task_id)
    if task is None:
        raise HTTPException(404, "Задача не найдена")
    ensure_project_access(db, user, task.project_id, write=True)
    if user.role != "admin" and db.scalar(
        select(ResourcePlan.assignment_id)
        .where(
            ResourcePlan.assignment_id == assignment_id,
            ResourcePlan.plan_month < app_today().replace(day=1),
        )
        .limit(1)
    ):
        raise HTTPException(
            403, "Назначение с планом прошедших месяцев снимает только администратор"
        )
    subject_user_id = assignment.user_id
    db.add(
        TaskActivity(
            task_id=task.task_id,
            user_id=user.user_id,
            change_type="assignment_removed",
            old_value=str(subject_user_id),
        )
    )
    db.execute(delete(ResourcePlan).where(ResourcePlan.assignment_id == assignment_id))
    db.delete(assignment)
    db.commit()
    audit(user.user_id, "delete", "task_assignments.users", [subject_user_id])
    return {"ok": True}


@router.get("/api/projects/{project_id}/calendar")
def get_calendar(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    project = ensure_project_access(db, user, project_id)
    ensure_calendar(db, project)
    db.commit()
    return {
        "items": [
            {"calendar_date": r.calendar_date, "working_hours": float(r.working_hours)}
            for r in db.scalars(
                select(Calendar)
                .where(Calendar.project_id == project_id)
                .order_by(Calendar.calendar_date)
            )
        ]
    }


@router.put("/api/projects/{project_id}/calendar", response_model=Result)
def update_calendar(
    project_id: int,
    body: CalendarUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    ensure_project_access(db, user, project_id, write=True)
    row = db.get(Calendar, (project_id, body.calendar_date))
    if row is None:
        db.add(Calendar(project_id=project_id, **body.model_dump()))
    else:
        row.working_hours = body.working_hours
    db.commit()
    return {"ok": True}
