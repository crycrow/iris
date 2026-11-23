from calendar import monthrange
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.common.models import Project, ProjectMember, User
from app.common.services.people import name_sort_key
from app.modules.time_tracking.models import (
    Task,
    TaskAssignment,
    ResourcePlan,
    TimeEntry,
    MetricSnapshot,
)
from app.modules.time_tracking.schemas.analytics import (
    DailyHours,
    TaskHours,
    EmployeeHours,
    HourTotals,
    MonthlyHours,
    ProjectAnalytics,
    WeeklyMetrics,
)
from .metrics import EVM
from .working_calendar import read_calendar


def month_starts(start: date, end: date) -> list[date]:

    result: list[date] = []
    current = start.replace(day=1)
    last = end.replace(day=1)
    while current <= last:
        result.append(current)
        if current == last:
            break
        current = date(current.year + (current.month == 12), current.month % 12 + 1, 1)
    return result


def report_period(
    as_of: date, date_from: date | None = None, date_to: date | None = None
) -> tuple[date, date]:
    start = date_from or as_of.replace(day=1)
    end = date_to or as_of.replace(day=monthrange(as_of.year, as_of.month)[1])
    if start > end:
        raise ValueError("Начало периода должно быть не позже окончания")
    return start, end


def planned_days(plan, task: Task, calendar: dict[date, float]) -> dict[date, Decimal]:
    first = max(plan.plan_month, task.start_date)
    last = min(
        plan.plan_month.replace(
            day=monthrange(plan.plan_month.year, plan.plan_month.month)[1]
        ),
        task.due_date,
    )
    if first > last:
        first = plan.plan_month
        last = first.replace(day=monthrange(first.year, first.month)[1])
    weights = {}
    current = first
    while current <= last:
        hours = Decimal(str(calendar.get(current, 0 if current.weekday() > 4 else 8)))
        if hours > 0:
            weights[current] = hours
        current += timedelta(days=1)
    if not weights and first <= last:
        weights = {
            first + timedelta(days=offset): Decimal(1)
            for offset in range((last - first).days + 1)
        }
    total = sum(weights.values(), Decimal(0))
    result = {}
    cumulative = allocated = Decimal(0)
    for day, hours in weights.items():
        cumulative += hours
        share = (Decimal(plan.planned_hours) * cumulative / total).quantize(
            Decimal("0.01")
        )
        result[day] = share - allocated
        allocated = share
    return result


def load_project_analytics(
    db: Session,
    project: Project,
    as_of: date,
    date_from: date | None = None,
    date_to: date | None = None,
    user_id: int | None = None,
) -> ProjectAnalytics:

    tasks = list(db.scalars(select(Task).where(Task.project_id == project.project_id)))
    parents = {task.parent_task_id for task in tasks if task.parent_task_id is not None}
    leaf_ids = [
        task.task_id
        for task in tasks
        if task.task_id not in parents
        and not task.is_milestone
        and task.status != "cancelled"
    ]
    plans = db.execute(
        select(
            ResourcePlan.plan_month,
            ResourcePlan.planned_hours,
            TaskAssignment.user_id,
            TaskAssignment.task_id,
        )
        .join(
            TaskAssignment, ResourcePlan.assignment_id == TaskAssignment.assignment_id
        )
        .where(TaskAssignment.task_id.in_(leaf_ids))
    ).all()

    entries = db.execute(
        select(
            TimeEntry.work_date,
            TimeEntry.user_id,
            TimeEntry.task_id,
            func.sum(TimeEntry.hours).label("hours"),
        )
        .join(Task, Task.task_id == TimeEntry.task_id)
        .where(Task.project_id == project.project_id, TimeEntry.work_date <= as_of)
        .group_by(TimeEntry.work_date, TimeEntry.user_id, TimeEntry.task_id)
        .order_by(TimeEntry.work_date)
    ).all()
    monday = as_of - timedelta(days=as_of.weekday())
    snapshots = list(
        db.scalars(
            select(MetricSnapshot)
            .where(
                MetricSnapshot.project_id == project.project_id,
                MetricSnapshot.task_id.is_(None),
                MetricSnapshot.user_id.is_(None),
                MetricSnapshot.week_start <= monday,
            )
            .order_by(MetricSnapshot.week_start)
        )
    )
    start, end = report_period(as_of, date_from, date_to)
    calendar = read_calendar(db, project.project_id)
    task_by_id = {task.task_id: task for task in tasks}
    first_month, last_month = start.replace(day=1), end.replace(day=1)
    monthly_plan: dict[date, Decimal] = defaultdict(Decimal)
    monthly_actual: dict[date, Decimal] = defaultdict(Decimal)
    person_plan: dict[int, Decimal] = defaultdict(Decimal)
    person_actual: dict[int, Decimal] = defaultdict(Decimal)
    daily_plan: dict[date, Decimal] = defaultdict(Decimal)
    task_actual: dict[int, Decimal] = defaultdict(Decimal)
    daily_actual: dict[date, Decimal] = defaultdict(Decimal)
    for plan in plans:
        if user_id is not None and plan.user_id != user_id:
            continue
        if first_month <= plan.plan_month <= last_month:
            for day, hours in planned_days(
                plan, task_by_id[plan.task_id], calendar
            ).items():
                if start <= day <= end:
                    daily_plan[day] += hours
                    monthly_plan[plan.plan_month] += hours
                    person_plan[plan.user_id] += hours
    for entry in entries:
        if user_id is not None and entry.user_id != user_id:
            continue
        if start <= entry.work_date <= end:
            hours = Decimal(entry.hours)
            monthly_actual[entry.work_date.replace(day=1)] += hours
            daily_actual[entry.work_date] += hours
            person_actual[entry.user_id] += hours
            task_actual[entry.task_id] += hours
    member_ids = set(
        db.scalars(
            select(ProjectMember.user_id).where(
                ProjectMember.project_id == project.project_id
            )
        )
    )
    available_ids = member_ids | {p.user_id for p in plans} | {e.user_id for e in entries}
    if user_id is not None and user_id not in available_ids:
        raise ValueError("Сотрудник не участвует в выбранном проекте")
    user_ids = {user_id} if user_id is not None else available_ids
    people = list(
        db.scalars(
            select(User)
            .where(User.user_id.in_(user_ids))
            .order_by(User.full_name, User.user_id)
        )
    )
    overall_actual = {
        user_id: Decimal(hours)
        for user_id, hours in db.execute(
            select(TimeEntry.user_id, func.sum(TimeEntry.hours))
            .where(
                TimeEntry.user_id.in_(user_ids),
                TimeEntry.work_date >= start,
                TimeEntry.work_date <= min(end, as_of),
            )
            .group_by(TimeEntry.user_id)
        )
    }
    weekly: list[WeeklyMetrics] = []
    for snapshot in snapshots:
        if start <= snapshot.week_start <= end:
            values = EVM(
                float(snapshot.bac),
                float(snapshot.pv),
                float(snapshot.ev),
                float(snapshot.ac),
            ).derived()
            weekly.append(
                WeeklyMetrics.model_validate(
                    {
                        **values,
                        "week_start": snapshot.week_start,
                        "is_current_week": snapshot.week_start == monday,
                    }
                )
            )
    daily_chart = (end - start).days < 31
    daily_days = (
        [start + timedelta(days=offset) for offset in range((end - start).days + 1)]
        if daily_chart
        else sorted(set(daily_plan) | set(daily_actual))
    )
    total_actual = sum(task_actual.values(), Decimal(0))
    task_hours = [
        TaskHours(
            task_id=task_id,
            name=task_by_id[task_id].name,
            actual_hours=float(hours),
            share_pct=(
                round(float(hours / total_actual) * 100, 2) if total_actual else 0
            ),
        )
        for task_id, hours in sorted(
            task_actual.items(), key=lambda row: (-row[1], task_by_id[row[0]].name)
        )
    ]
    distribution = list(task_hours[:6])
    if len(task_hours) > 6:
        other = sum(
            (Decimal(str(row.actual_hours)) for row in task_hours[6:]), Decimal(0)
        )
        distribution.append(
            TaskHours(
                name="Другие задачи",
                actual_hours=float(other),
                share_pct=round(float(other / total_actual) * 100, 2),
            )
        )
    return ProjectAnalytics(
        project_id=project.project_id,
        as_of=as_of,
        date_from=start,
        date_to=end,
        chart_granularity="day" if daily_chart else "month",
        monthly=[
            MonthlyHours(
                month=month,
                planned_hours=float(monthly_plan[month]),
                actual_hours=(
                    float(monthly_actual[month])
                    if month <= as_of.replace(day=1)
                    else None
                ),
                is_future=month > as_of.replace(day=1),
            )
            for month in month_starts(start, end)
        ],
        weekly=weekly if user_id is None else [],
        employees=[
            EmployeeHours(
                user_id=person.user_id,
                full_name=person.full_name,
                planned_hours=float(person_plan[person.user_id]),
                actual_hours=float(person_actual[person.user_id]),
                total_actual_hours=float(overall_actual.get(person.user_id, 0)),
                project_share_pct=(
                    round(
                        float(
                            person_actual[person.user_id]
                            / overall_actual[person.user_id]
                        )
                        * 100,
                        2,
                    )
                    if overall_actual.get(person.user_id)
                    else None
                ),
            )
            for person in sorted(people, key=lambda person: name_sort_key(person.full_name, person.user_id))
        ],
        daily=[
            DailyHours(
                work_date=day,
                planned_hours=float(daily_plan[day]),
                actual_hours=float(daily_actual[day]) if day <= as_of else None,
            )
            for day in daily_days
        ],
        task_hours=task_hours,
        task_distribution=distribution,
        totals=HourTotals(
            planned_hours=float(sum(monthly_plan.values(), Decimal(0))),
            actual_hours=float(sum(monthly_actual.values(), Decimal(0))),
        ),
        notes=[],
    )
