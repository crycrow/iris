from collections import Counter
from datetime import date, timedelta
import math
from sqlalchemy import select
from app.common.models import Project
from app.common.services.people import name_sort_key
from .task_view import plan_tree
from app.core.clock import today
from app.modules.time_tracking.models import Task
from .analytics import load_project_analytics
from .working_calendar import read_calendar, settings_values
import json

TASK_LABELS = {
    "backlog": "Бэклог",
    "todo": "Пора делать",
    "dev": "В разработке",
    "review": "Проверка",
    "testing": "Тестирование",
    "release_wait": "Ожидает релиза",
    "done": "Готово",
    "cancelled": "Отклонена",
}


def labor_sections(
    db, project: Project, date_from: date | None = None, date_to: date | None = None, user_id: int | None = None
) -> list[dict]:
    data = load_project_analytics(db, project, today(), date_from, date_to, user_id)
    return [
        {
            "title": "Трудозатраты по месяцам",
            "headers": [
                "Месяц",
                "План за период, ч",
                "Фактически учтено, ч",
                "Разница, ч",
            ],
            "rows": [
                [
                    m.month.strftime("%m.%Y"),
                    m.planned_hours,
                    m.actual_hours,
                    (
                        m.actual_hours - m.planned_hours
                        if m.actual_hours is not None
                        else None
                    ),
                ]
                for m in data.monthly
            ],
            "chart": {"columns": [1, 2]} if data.chart_granularity == "month" else None,
        },
        {
            "title": "Участие сотрудников",
            "headers": [
                "Сотрудник",
                "Назначено, ч",
                "Учтено, ч",
                "Всего по всем проектам, ч",
                "Доля загрузки на проекте, %",
            ],
            "rows": [
                [
                    e.full_name,
                    e.planned_hours,
                    e.actual_hours,
                    e.total_actual_hours,
                    e.project_share_pct,
                ]
                for e in sorted(data.employees, key=lambda e: name_sort_key(e.full_name, e.user_id))
            ],
        },
        {
            "title": "Учёт по дням",
            "headers": ["Дата", "План, ч", "Учтено, ч"],
            "rows": [
                [d.work_date, d.planned_hours, d.actual_hours] for d in data.daily
            ],
            "chart": {"columns": [1, 2]} if data.chart_granularity == "day" else None,
        },
        {
            "title": "Трудозатраты по задачам",
            "headers": ["Задача", "Учтено, ч", "Доля факта проекта, %"],
            "rows": [
                [t.name, t.actual_hours, t.share_pct] for t in data.task_distribution
            ],
            "chart": {"type": "bar", "columns": [1]},
        },
    ]


def delivery_data(db, project_id: int) -> dict:
    tasks = list(
        db.scalars(
            select(Task)
            .where(Task.project_id == project_id)
            .order_by(Task.due_date, Task.task_id)
        )
    )
    parents = {task.parent_task_id for task in tasks if task.parent_task_id}
    active = [
        task
        for task in tasks
        if not task.is_milestone
        and task.task_id not in parents
        and task.status != "cancelled"
    ]
    completed = sum(task.status == "done" for task in active)
    unfinished = [task for task in active if task.status != "done"]
    return {
        "task_count": len(active),
        "completed": completed,
        "overdue": sum(task.due_date < today() for task in unfinished),
        "completion": round(completed / len(active) * 100, 1) if active else 0,
        "states": [
            [TASK_LABELS[state], count]
            for state, count in Counter(task.status for task in active).items()
        ],
        "milestones": [
            [
                task.name,
                task.due_date,
                TASK_LABELS[task.status],
                (
                    "Просрочена"
                    if task.due_date < today() and task.status != "done"
                    else "Завершена" if task.status == "done" else "В плане"
                ),
            ]
            for task in tasks
            if task.is_milestone and task.status != "cancelled"
        ],
        "upcoming": [
            [
                task.name,
                task.due_date,
                TASK_LABELS[task.status],
                float(task.progress_pct),
            ]
            for task in unfinished[:10]
        ],
    }


def summary_sections(db, project: Project, data: dict) -> list[dict]:
    metrics, delivery = data.get("metrics", {}), data.get("delivery", {})
    forecast = schedule_forecast(db, project, metrics)
    impact = forecast["risk_impact"]
    return [
        {
            "title": "Состояние проекта",
            "headers": ["Показатель", "Значение"],
            "rows": [
                ["Начало проекта", project.start_date],
                ["Плановое завершение", project.end_date],
                ["Завершено задач, %", delivery.get("completion", 0)],
                ["Задач с нарушенным сроком", delivery.get("overdue", 0)],
                ["Прогноз завершения", forecast["forecast_date"]],
                ["Задержка, рабочие дни", forecast["delay_days"]],
                ["План трудозатрат, ч", metrics.get("bac")],
                ["Прогноз итоговых трудозатрат, ч", metrics.get("eac")],
            ],
        },
        {
            "title": "Выполнение задач",
            "headers": ["Состояние", "Количество задач"],
            "rows": delivery.get("states", []),
            "chart": {"type": "doughnut", "columns": [1], "unit": "задач"},
        },
        {
            "title": "Контрольные точки",
            "headers": ["Контрольная точка", "Срок", "Состояние", "Выполнение срока"],
            "rows": delivery.get("milestones", []),
            "row_styles": [{"milestone": True} for _ in delivery.get("milestones", [])],
        },
        {
            "title": "Риски выполнения проекта",
            "headers": ["Показатель", "Значение"],
            "rows": [["Незавершённых задач с действующими рисками", impact["tasks"]],
                     ["Контрольных точек с действующими рисками", impact["milestones"]],
                     ["Просроченных задач и вех с рисками", impact["overdue"]],
                     ["Рисков без ответственного", impact["unassigned"]]],
        },
        {
            "title": "Зоны, требующие решения",
            "headers": ["Объект", "Плановый срок", "Открытых рисков", "Критических", "Ответственные", "Необходимое решение"],
            "rows": [[z["target"], z["deadline"], z["open"], z["critical"], z["owners"], z["decision"]] for z in impact["zones"]],
        },
        {
            "title": "Ближайшие работы",
            "headers": ["Задача", "Срок", "Состояние", "Готовность, %"],
            "rows": delivery.get("upcoming", []),
        },
    ]


def schedule_forecast(db, project: Project, metrics: dict) -> dict:
    from app.modules.risk_management.services.reporting import delivery_impact
    shift = metrics.get("s")
    result: dict = {
        "planned_date": project.end_date,
        "forecast_date": None,
        "delay_days": None,
        "is_completed": project.status == "completed",
        "risk_impact": delivery_impact(db, project.project_id),
    }
    if shift is None or not math.isfinite(float(shift)) or result["is_completed"]:
        return result
    calendar = read_calendar(db, project.project_id)
    settings = settings_values(db)
    holidays = set(json.loads(settings.get("calendar_holidays", "[]")))
    overrides = json.loads(settings.get("calendar_overrides", "{}"))

    def working(day):
        return (
            calendar.get(
                day,
                overrides.get(
                    day.isoformat(),
                    0 if day.weekday() > 4 or day.isoformat() in holidays else 8,
                ),
            )
            > 0
        )

    days = math.ceil(float(shift)) if float(shift) >= 0 else math.floor(float(shift))
    if abs(days) > 36500:
        return result
    forecast = project.end_date
    remaining = abs(days)
    direction = 1 if days >= 0 else -1
    iterations = 0
    while remaining and iterations < 100000:
        forecast += timedelta(days=direction)
        if working(forecast):
            remaining -= 1
        iterations += 1
    if remaining:
        return result
    forecast = max(forecast, today())
    delay = 0
    cursor = project.end_date + timedelta(days=1)
    while cursor <= forecast:
        delay += working(cursor)
        cursor += timedelta(days=1)
    result.update(forecast_date=forecast, delay_days=delay)
    return result


def calendar_plan_section(tasks: list[dict]) -> dict:

    ordered = sorted(tasks, key=lambda t: (t["start_date"], t["task_id"]))
    rows, styles = [], []
    def append(nodes, depth=0):
        for task in nodes:
            rows.append([
                f'{task["wbs"]}  {task["name"]}', task["start_date"], task["due_date"],
                TASK_LABELS[task["status"]], task["progress_pct"],
                task["planned_hours"], task["actual_hours"],
            ])
            styles.append({"depth": depth, "bold": bool(task["children"]),
                           "milestone": bool(task["is_milestone"])})
            append(task["children"], depth + 1)
    append(plan_tree(ordered))
    return {"title": "Календарный план", "headers": ["Задача", "Начало", "Окончание", "Статус", "Прогресс, %", "План, ч", "Факт, ч"],
            "rows": rows, "row_styles": styles}
