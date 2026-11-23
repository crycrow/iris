from app.core.clock import today as app_today
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.common.models import User, Project, ProjectMember
from app.common.services.people import name_sort_key
from app.common.permissions import get_current_user, ensure_project_access
from app.common.services.access_log import audit
from app.common.exports.xlsx_base import make_xlsx, make_report_xlsx
from app.common.exports.pdf_base import make_pdf, make_report_pdf
from app.modules.time_tracking.models import Task
from app.modules.time_tracking.services.task_view import task_rows
from app.modules.time_tracking.services.snapshots import compute_project_metrics
from .resources import resource_plan
from app.common.services.project_summary import register_provider
from app.modules.time_tracking.services.analytics import report_period
from app.modules.time_tracking.services.reporting import (
    labor_sections,
    delivery_data,
    summary_sections,
    schedule_forecast,
    calendar_plan_section,
)

register_provider("delivery", delivery_data)
register_provider(
    "summary_sections",
    lambda db, pid, data: summary_sections(db, db.get(Project, pid), data),
)

router = APIRouter(tags=["Отчёты по трудозатратам"])


@router.get("/api/reports/time-tracking")
def labor_report(
    project_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    if user.role == "employee":
        raise HTTPException(403, "Доступно руководителям проектов и администраторам")
    query = select(Project)
    if user.role == "manager":
        query = query.where(Project.manager_id == user.user_id)
    if project_id:
        ensure_project_access(db, user, project_id, write=True)
        query = query.where(Project.project_id == project_id)
    projects = list(db.scalars(query))
    data = compute_project_metrics(db, app_today(), [p.project_id for p in projects])
    tasks = {
        t.task_id: t
        for t in db.scalars(
            select(Task).where(Task.project_id.in_([p.project_id for p in projects]))
        )
    }
    names = {p.project_id: p.name for p in projects}
    viewed_users = list(
        db.scalars(
            select(ProjectMember.user_id)
            .where(ProjectMember.project_id.in_(list(names)))
            .distinct()
        )
    )
    audit(user.user_id, "read", "labor_report.users", viewed_users)
    db.commit()
    return {
        "projects": [
            {**row, "name": names[pid]} for pid, row in data["projects"].items()
        ],
        "tasks": [
            {**row, "name": tasks[tid].name, "project_name": names[row["project_id"]]}
            for tid, row in data["tasks"].items()
        ],
    }


@router.get("/api/projects/{project_id}/export/{kind}.{format}")
def export_report(
    project_id: int,
    kind: str,
    format: str,
    date_from: date | None = None,
    date_to: date | None = None,
    user_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    project = ensure_project_access(db, user, project_id, write=True)
    if format not in ("xlsx", "pdf") or kind not in ("plan", "resources", "labor"):
        raise HTTPException(404, "Формат отчёта не найден")
    if kind == "plan":
        tasks = task_rows(
            db,
            list(
                db.scalars(
                    select(Task)
                    .where(Task.project_id == project_id)
                    .order_by(Task.start_date)
                )
            ),
        )
        sections = [calendar_plan_section(tasks)]
        title = "Календарный план"
    elif kind == "resources":
        data = resource_plan(project_id, db, user)
        months = [
            month
            for month in data["months"]
            if project.start_date.strftime("%Y-%m")
            <= month
            <= project.end_date.strftime("%Y-%m")
            or any(
                m["plan"] or m["fact"]
                for row in data["rows"]
                for m in row["months"]
                if m["month"] == month
            )
        ]
        headers = [
            "Сотрудник",
            *[f"{month} {label}, ч" for month in months for label in ("план", "факт")],
        ]
        rows = [
            [
                row["full_name"],
                *[
                    value
                    for m in row["months"]
                    if m["month"] in months
                    for value in (m["plan"], m["fact"])
                ],
            ]
            for row in sorted(data["rows"], key=lambda row: name_sort_key(row["full_name"]))
        ]
        title = "Ресурсный план"
    else:
        try:
            period_start, period_end = report_period(app_today(), date_from, date_to)
            sections = labor_sections(db, project, period_start, period_end, user_id)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        title = f"Трудозатраты за {period_start:%d.%m.%Y} по {period_end:%d.%m.%Y}"
        if user_id is not None:
            title += f". {db.get(User, user_id).full_name}"
    if kind in ("labor", "plan"):
        content = (make_report_pdf if format == "pdf" else make_report_xlsx)(
            f"{title}. {project.name}", sections
        )
    elif kind == "resources" and format == "pdf":
        sections = []
        for start in range(0, len(months), 3):
            columns = [0, *range(1 + start * 2, 1 + min(start + 3, len(months)) * 2)]
            sections.append(
                {
                    "title": "Ресурсный план " + ", ".join(months[start : start + 3]),
                    "headers": [headers[col] for col in columns],
                    "rows": [[row[col] for col in columns] for row in rows],
                }
            )
        content = make_report_pdf(f"{title}. {project.name}", sections)
    else:
        content = (make_pdf if format == "pdf" else make_xlsx)(
            f"{title}. {project.name}", headers, rows
        )
    viewed_users = list(
        db.scalars(
            select(ProjectMember.user_id).where(ProjectMember.project_id == project_id)
        )
    )
    audit(user.user_id, "export", f"{kind}.{format}.users", viewed_users)
    media = (
        "application/pdf"
        if format == "pdf"
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    return Response(
        content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{kind}.{format}"'},
    )


@router.get("/api/projects/{project_id}/schedule-forecast")
def project_schedule_forecast(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    project = ensure_project_access(db, user, project_id, write=True)
    metrics = compute_project_metrics(db, app_today(), [project_id])["projects"].get(
        project_id, {}
    )
    return schedule_forecast(db, project, metrics)
