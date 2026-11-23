from app.core.clock import today as local_today
from datetime import date, timedelta
from dataclasses import asdict
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.common.models import User, Project
from app.common.permissions import (
    require_roles,
    get_current_user,
    accessible_project_ids,
)
from app.common.routers.projects import register_calendar_provider
from app.common.services.project_summary import register_provider
from app.modules.time_tracking.models import Task, TaskAssignment, TimeEntry, Calendar
from app.modules.time_tracking.services.working_calendar import ensure_calendar
from app.modules.time_tracking.services.timesheet import previous_week_status
from app.modules.time_tracking.services.snapshots import (
    compute_and_store_snapshot,
    compute_project_metrics,
)
from app.modules.risk_management.models import Risk
from app.modules.risk_management.services.engine import run_risk_scan

router = APIRouter(tags=["Совместная работа модулей"])


def configure_providers() -> None:
    register_calendar_provider(ensure_calendar)
    register_provider(
        "metrics",
        lambda db, pid: compute_project_metrics(db, local_today(), [pid])[
            "projects"
        ].get(pid, {}),
    )
    register_provider(
        "risks",
        lambda db, pid: [
            {
                "risk_id": r.risk_id,
                "status": r.status,
                "description": r.description,
                "is_cause_resolved": r.is_cause_resolved,
            }
            for r in db.scalars(select(Risk).where(Risk.project_id == pid))
        ],
    )


def can_remove_members(db: Session, project_id: int, user_ids: set[int]) -> bool:
    return (
        db.scalar(
            select(TaskAssignment.assignment_id)
            .join(Task)
            .where(Task.project_id == project_id, TaskAssignment.user_id.in_(user_ids))
            .limit(1)
        )
        is None
    )


def analyze(
    db: Session,
    as_of: date,
    initiator_id: int | None = None,
    project_ids: list[int] | None = None,
) -> dict:

    if db.get_bind().dialect.name == "postgresql":
        from sqlalchemy import text

        db.execute(text("SELECT pg_advisory_xact_lock(847195)"))
    snapshot = compute_and_store_snapshot(db, as_of, project_ids)
    scan = run_risk_scan(db, as_of, initiator_id, project_ids=project_ids)
    return {"snapshot": asdict(snapshot), "scan": scan}


@router.post("/api/risks/scan")
def scan(
    user: User = Depends(require_roles("admin", "manager")),
    db: Session = Depends(get_db),
):
    ids = (
        None
        if user.role == "admin"
        else list(
            db.scalars(
                select(Project.project_id).where(Project.manager_id == user.user_id)
            )
        )
    )
    result = analyze(db, local_today(), user.user_id, ids)
    db.commit()
    return result


@router.get("/api/dashboard")
def dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ids = accessible_project_ids(db, user)
    today = local_today()
    monday = today - timedelta(days=today.weekday())
    previous_week = previous_week_status(db, user, today)
    tasks = list(
        db.scalars(
            select(Task)
            .join(TaskAssignment)
            .where(
                TaskAssignment.user_id == user.user_id,
                Task.project_id.in_(ids),
                Task.status.not_in(("done", "cancelled")),
            )
        )
    )
    last = db.scalar(
        select(func.max(TimeEntry.work_date))
        .join(Task)
        .where(
            TimeEntry.user_id == user.user_id,
            TimeEntry.work_date <= today,
            Task.project_id.in_(ids),
        )
    )
    start = last or min((t.start_date for t in tasks), default=today)
    days = set(
        db.scalars(
            select(Calendar.calendar_date).where(
                Calendar.project_id.in_(ids),
                Calendar.calendar_date > start,
                Calendar.calendar_date <= today,
                Calendar.working_hours > 0,
            )
        )
    )
    risks = list(
        db.scalars(
            select(Risk).where(
                (Risk.project_id.in_(ids))
                | (
                    (Risk.project_id.is_(None)) & (Risk.subject_user_id == user.user_id)
                ),
                Risk.status.in_(("new", "reviewing", "in_progress")),
            )
        )
    )
    projects = list(db.scalars(select(Project).where(Project.project_id.in_(ids))))
    from app.common.routers.projects import serialize

    return {
        "role": user.role,
        "today": today,
        "projects": [serialize(db, p) for p in projects],
        "my_tasks": [
            {
                "task_id": t.task_id,
                "project_id": t.project_id,
                "name": t.name,
                "status": t.status,
                "progress_pct": t.progress_pct,
                "due_date": t.due_date,
            }
            for t in tasks
        ],
        "hours_week": float(
            db.scalar(
                select(func.coalesce(func.sum(TimeEntry.hours), 0))
                .join(Task)
                .where(
                    TimeEntry.user_id == user.user_id,
                    Task.project_id.in_(ids),
                    TimeEntry.work_date >= monday,
                    TimeEntry.work_date <= today,
                )
            )
        ),
        "hours_month": float(
            db.scalar(
                select(func.coalesce(func.sum(TimeEntry.hours), 0))
                .join(Task)
                .where(
                    TimeEntry.user_id == user.user_id,
                    Task.project_id.in_(ids),
                    TimeEntry.work_date >= today.replace(day=1),
                    TimeEntry.work_date <= today,
                )
            )
        ),
        "open_risks": len(risks),
        "new_risks_count": sum(not r.is_viewed for r in risks),
        "last_entry_date": last,
        "no_entry_workdays": len(days),
        "filled_last_week": not previous_week["missing"],
        "missing_time_warning": previous_week["missing"],
        "previous_week": previous_week,
        "projects_total": len(projects),
        "projects_active": sum(p.status == "active" for p in projects),
        "users_total": (
            db.scalar(select(func.count(User.user_id)))
            if user.role == "admin"
            else None
        ),
    }
