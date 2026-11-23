from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.common.models import User
from app.common.services.people import name_sort_key
from app.modules.time_tracking.models import (
    Task,
    TaskAssignment,
    ResourcePlan,
    TimeEntry,
)


def task_rows(db: Session, tasks: list[Task]) -> list[dict]:
    ids = [t.task_id for t in tasks]
    assignment_rows = list(
        db.execute(
            select(TaskAssignment, User.full_name)
            .join(User, User.user_id == TaskAssignment.user_id)
            .where(TaskAssignment.task_id.in_(ids))
        )
    )
    assignment_rows.sort(key=lambda row: name_sort_key(row[1], row[0].user_id))
    hours = {
        key: value
        for key, value in db.execute(
            select(
                ResourcePlan.assignment_id, func.sum(ResourcePlan.planned_hours)
            ).group_by(ResourcePlan.assignment_id)
        )
    }
    actual = {
        key: value
        for key, value in db.execute(
            select(TimeEntry.task_id, func.sum(TimeEntry.hours))
            .where(TimeEntry.task_id.in_(ids))
            .group_by(TimeEntry.task_id)
        )
    }
    result = []
    for task in tasks:
        assignments = [
            {
                "assignment_id": a.assignment_id,
                "user_id": a.user_id,
                "full_name": name,
                "planned_hours": float(hours.get(a.assignment_id, 0)),
            }
            for a, name in assignment_rows
            if a.task_id == task.task_id
        ]
        result.append(
            {
                **{c.name: getattr(task, c.name) for c in Task.__table__.columns},
                "assignments": assignments,
                "planned_hours": sum(a["planned_hours"] for a in assignments),
                "actual_hours": float(actual.get(task.task_id, 0)),
            }
        )
    return result


def plan_tree(rows: list[dict]) -> list[dict]:
    nodes = {row["task_id"]: {**row, "children": []} for row in rows}
    roots = []
    for node in nodes.values():
        if node["parent_task_id"] in nodes:
            nodes[node["parent_task_id"]]["children"].append(node)
        else:
            roots.append(node)

    def visit(children: list[dict], prefix: str = "") -> None:
        for i, node in enumerate(children, 1):
            node["wbs"] = f"{prefix}{i}"
            visit(node["children"], node["wbs"] + ".")
            if node["children"]:
                active = [
                    child
                    for child in node["children"]
                    if child["status"] != "cancelled"
                ]
                node["planned_hours"] = sum(child["planned_hours"] for child in active)
                node["actual_hours"] = sum(child["actual_hours"] for child in active)
                node["progress_pct"] = (
                    round(
                        sum(
                            child["planned_hours"] * child["progress_pct"]
                            for child in active
                        )
                        / node["planned_hours"]
                    )
                    if node["planned_hours"]
                    else 0
                )

    visit(roots)
    return roots
