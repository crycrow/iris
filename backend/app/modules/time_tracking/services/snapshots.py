from app.core.clock import today as app_today

"""Пакетный расчёт без запросов к базе внутри формул."""
from calendar import monthrange
from typing import Any
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.common.models import Project, ProjectMember
from app.modules.time_tracking.models import (
    Task,
    TaskAssignment,
    ResourcePlan,
    TimeEntry,
    Calendar,
    MetricSnapshot,
)
from .metrics import (
    task_evm,
    aggregate,
    working_days,
    overdue_days,
    days_without_entries,
    forecast_delay,
    progress,
    utilization,
    remaining_work,
    participant_share,
    team_capacity,
)
from .working_calendar import ensure_calendar, settings_values


@dataclass
class SnapshotResult:
    week_start: date
    created: int = 0
    updated: int = 0
    preserved: int = 0


def compute_project_metrics(
    db: Session, as_of: date, project_ids: list[int] | None = None
) -> dict:
    projects = list(db.scalars(select(Project)))
    selected = [
        p
        for p in projects
        if (
            p.project_id in project_ids
            if project_ids is not None
            else p.status == "active"
        )
    ]
    for project in projects:
        ensure_calendar(db, project, as_of)
    calendars: dict[int, dict[date, float]] = defaultdict(dict)
    for calendar_row in db.scalars(select(Calendar)):
        calendars[calendar_row.project_id][calendar_row.calendar_date] = float(
            calendar_row.working_hours
        )
    tasks = list(db.scalars(select(Task)))
    task_map = {t.task_id: t for t in tasks}
    parent_ids = {t.parent_task_id for t in tasks if t.parent_task_id}
    assignments = list(db.scalars(select(TaskAssignment)))
    assignment_map = {a.assignment_id: a for a in assignments}
    plans = list(db.scalars(select(ResourcePlan)))
    plan_hours: dict[int, float] = defaultdict(float)
    user_month: dict[tuple[int, date], float] = defaultdict(float)
    for plan_row in plans:
        assignment = assignment_map[plan_row.assignment_id]
        task = task_map[assignment.task_id]
        if (
            task.status == "cancelled"
            or task.task_id in parent_ids
            or task.is_milestone
        ):
            continue
        plan_hours[assignment.assignment_id] += float(plan_row.planned_hours)
        user_month[assignment.user_id, plan_row.plan_month] += float(
            plan_row.planned_hours
        )
    task_hours: dict[int, float] = defaultdict(float)
    for assignment in assignments:
        task_hours[assignment.task_id] += plan_hours[assignment.assignment_id]
    entries_by_task: dict[int, list[tuple[date, float]]] = defaultdict(list)
    user_week: dict[int, float] = defaultdict(float)
    monday = as_of - timedelta(days=as_of.weekday())
    for entry_row in db.scalars(select(TimeEntry).where(TimeEntry.work_date <= as_of)):
        entries_by_task[entry_row.task_id].append(
            (entry_row.work_date, float(entry_row.hours))
        )
        if entry_row.work_date >= monday:
            user_week[entry_row.user_id] += float(entry_row.hours)
    members: dict[int, set[int]] = defaultdict(set)
    for member_row in db.scalars(select(ProjectMember)):
        members[member_row.project_id].add(member_row.user_id)
    user_calendars: dict[int, dict[date, float]] = {}
    for calendar_project_id in sorted(members):
        for member_id in members[calendar_project_id]:
            user_calendars.setdefault(member_id, calendars[calendar_project_id])
    daily = float(settings_values(db).get("daily_hours", "8"))
    result: dict[str, dict[Any, dict[str, Any]]] = {
        "projects": {},
        "tasks": {},
        "members": {},
        "users": {},
    }
    for project in selected:
        pid = project.project_id
        calendar = calendars[pid]
        leaf_tasks = [
            t
            for t in tasks
            if t.project_id == pid
            and t.task_id not in parent_ids
            and t.status != "cancelled"
        ]
        evms = []
        user_remaining: dict[int, float] = defaultdict(float)
        for task in leaf_tasks:
            evm = task_evm(
                task_hours[task.task_id],
                task.start_date,
                task.due_date,
                task.status,
                task.progress_pct,
                entries_by_task[task.task_id],
                calendar,
                as_of,
                task.is_milestone,
            )
            evms.append(evm)
            last = max((d for d, _ in entries_by_task[task.task_id]), default=None)
            result["tasks"][task.task_id] = {
                "project_id": pid,
                "task_id": task.task_id,
                **evm.derived(),
                "delta_t": overdue_days(
                    calendar, task.due_date, as_of, task.status == "done"
                ),
                "t_safe": days_without_entries(
                    calendar, task.start_date, last, as_of, task.status
                ),
            }
            if task.status != "done":
                for assignment in assignments:
                    if assignment.task_id == task.task_id:
                        user_remaining[assignment.user_id] += remaining_work(
                            plan_hours[assignment.assignment_id],
                            progress(task.status, task.progress_pct),
                        )
        total = aggregate(evms)
        delta = overdue_days(
            calendar,
            project.end_date,
            as_of,
            project.status in ("completed", "cancelled"),
        )
        duration = working_days(calendar, project.start_date, project.end_date)
        remaining_days = working_days(
            calendar, as_of + timedelta(days=1), project.end_date
        )
        other_hours: dict[int, float] = defaultdict(float)
        for plan_row in plans:
            assignment = assignment_map[plan_row.assignment_id]
            task = task_map[assignment.task_id]
            if (
                assignment.user_id not in members[pid]
                or task.project_id == pid
                or task.status in ("done", "cancelled")
                or task.task_id in parent_ids
            ):
                continue
            month_end = plan_row.plan_month.replace(
                day=monthrange(plan_row.plan_month.year, plan_row.plan_month.month)[1]
            )
            start = max(as_of + timedelta(days=1), plan_row.plan_month)
            end = min(project.end_date, month_end)
            other_calendar = calendars[task.project_id]
            month_days = working_days(other_calendar, plan_row.plan_month, month_end)
            fraction = (
                working_days(other_calendar, start, end) / month_days
                if start <= end and month_days
                else 0
            )
            other_hours[assignment.user_id] += float(plan_row.planned_hours) * fraction
        w = sum(user_remaining.values())
        result["projects"][pid] = {
            "project_id": pid,
            **total.derived(),
            "delta_t": delta,
            "s": forecast_delay(
                total, duration, delta, project.status in ("completed", "cancelled")
            ),
            "w": w,
            "m": team_capacity(
                remaining_days, [other_hours[uid] for uid in members[pid]], daily
            ),
        }
        for uid in members[pid]:
            result["members"][pid, uid] = {
                "project_id": pid,
                "user_id": uid,
                "w": user_remaining[uid],
                "k": participant_share(user_remaining[uid], w),
            }
            current_month = as_of.replace(day=1)
            next_month = date(as_of.year + (as_of.month == 12), as_of.month % 12 + 1, 1)

            if uid not in result["users"]:
                norm_calendar = user_calendars[uid]
                current_days = working_days(
                    norm_calendar,
                    current_month,
                    current_month.replace(day=monthrange(as_of.year, as_of.month)[1]),
                )
                next_days = working_days(
                    norm_calendar,
                    next_month,
                    next_month.replace(
                        day=monthrange(next_month.year, next_month.month)[1]
                    ),
                )
                week_days = working_days(
                    norm_calendar, monday, monday + timedelta(days=6)
                )
                result["users"][uid] = {
                    "user_id": uid,
                    "u_plan": utilization(
                        user_month[uid, current_month], current_days, daily
                    ),
                    "u_plan_next": utilization(
                        user_month[uid, next_month], next_days, daily
                    ),
                    "u_fact": utilization(user_week[uid], week_days, daily),
                }
    return result


def compute_and_store_snapshot(
    db: Session, as_of: date, project_ids: list[int] | None = None
) -> SnapshotResult:
    monday = as_of - timedelta(days=as_of.weekday())
    current = app_today() - timedelta(days=app_today().weekday())
    if monday > current:
        raise ValueError("Нельзя сохранять срез будущей недели")
    result = SnapshotResult(week_start=monday)
    metrics = compute_project_metrics(db, as_of, project_ids)
    stored = {
        (r.project_id, r.task_id, r.user_id): r
        for r in db.scalars(
            select(MetricSnapshot).where(MetricSnapshot.week_start == monday)
        )
    }
    frozen_projects = (
        {key[0] for key in stored if key[0] is not None} if monday < current else set()
    )
    allowed = {c.name for c in MetricSnapshot.__table__.columns} - {"snapshot_id"}
    for group in metrics.values():
        for values in group.values():
            key = (
                values.get("project_id"),
                values.get("task_id"),
                values.get("user_id"),
            )
            row = stored.get(key)
            if monday < current and (row is not None or key[0] in frozen_projects):
                result.preserved += 1
                continue
            data = {k: v for k, v in values.items() if k in allowed}
            if row is None:
                row = MetricSnapshot(week_start=monday, **data)
                db.add(row)
                result.created += 1
            else:
                for name, value in data.items():
                    setattr(row, name, value)
                result.updated += 1
    db.flush()
    return result
