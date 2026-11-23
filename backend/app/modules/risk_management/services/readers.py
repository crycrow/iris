from datetime import date, timedelta
from collections import defaultdict
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.core.database import Base
from app.common.models import ProjectMember

from app.modules.time_tracking.models import Task, TaskAssignment


def load_context(db: Session, as_of: date, project_ids: list[int]) -> dict:

    table = Base.metadata.tables["metric_snapshots"]
    week = as_of - timedelta(days=as_of.weekday())
    rows = (
        db.execute(
            select(table)
            .where(table.c.week_start <= week)
            .order_by(table.c.week_start.desc())
        )
        .mappings()
        .all()
    )
    histories: dict[tuple, list[dict]] = defaultdict(list)
    members: dict[int, set[int]] = defaultdict(set)
    for member in db.execute(
        select(ProjectMember).where(ProjectMember.project_id.in_(project_ids))
    ).scalars():
        members[member.project_id].add(member.user_id)
    allowed_users = set().union(*members.values()) if members else set()
    for row in rows:
        if row["project_id"] not in project_ids and not (
            row["project_id"] is None and row["user_id"] in allowed_users
        ):
            continue
        histories[(row["project_id"], row["task_id"], row["user_id"])].append(dict(row))
    tasks = {
        t.task_id: t
        for t in db.scalars(select(Task).where(Task.project_id.in_(project_ids)))
    }
    active_users = set(
        db.scalars(
            select(TaskAssignment.user_id)
            .join(Task, Task.task_id == TaskAssignment.task_id)
            .where(
                Task.project_id.in_(project_ids),
                Task.status.notin_(["done", "cancelled"]),
                Task.is_milestone.is_(False),
            )
        )
    )
    activity = Base.metadata.tables["task_activity"]
    completions = {
        tid: changed
        for tid, changed in db.execute(
            select(activity.c.task_id, func.max(activity.c.changed_at))
            .where(activity.c.new_value == "done", activity.c.change_type == "status")
            .group_by(activity.c.task_id)
        )
    }
    return {
        "histories": histories,
        "members": members,
        "active_users": active_users,
        "tasks": tasks,
        "completions": completions,
        "week": week,
        "as_of": as_of,
    }


def get_task(db: Session, task_id: int) -> Task | None:
    return db.get(Task, task_id)


def task_names(db: Session, ids: list[int]) -> dict[int, str]:
    return {
        tid: name
        for tid, name in db.execute(
            select(Task.task_id, Task.name).where(Task.task_id.in_(ids))
        )
    }
