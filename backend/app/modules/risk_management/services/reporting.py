from collections import Counter
from datetime import date, timedelta
from app.core.clock import today
from app.common.services.people import name_sort_key

OPEN = {"new", "reviewing", "in_progress"}
SEVERITIES = {"critical": "Критическая", "high": "Высокая", "medium": "Средняя"}
STATUSES = {
    "new": "Новый",
    "reviewing": "На рассмотрении",
    "in_progress": "В работе",
    "closed": "Закрыт",
    "rejected": "Отклонён",
}


def analysis_period(
    date_from: date | None, date_to: date | None
) -> tuple[date | None, date | None]:
    if date_from and date_to and date_from > date_to:
        raise ValueError("Начало периода должно быть не позже окончания")
    return date_from, date_to


def risk_timeline(items: list[dict], start: date | None, end: date | None) -> dict:
    counts = Counter(date.fromisoformat(str(row["detected_at"])[:10]) for row in items)
    result: dict = {"granularity": "day", "title": "Выявление рисков", "points": []}
    if not counts:
        return result
    lower = start or min(counts)
    upper = min(end, today()) if end else today() if start else max(counts)
    if upper < lower:
        return result
    days = (upper - lower).days + 1
    granularity = "day" if days <= 45 else "week" if days <= 180 else "month"
    titles = {
        "day": "Выявлено рисков по дням",
        "week": "Выявлено рисков по неделям",
        "month": "Выявлено рисков по месяцам",
    }
    points = []
    current = lower
    while current <= upper:
        if granularity == "day":
            finish = current
        elif granularity == "week":
            finish = min(upper, current + timedelta(days=6 - current.weekday()))
        else:
            next_month = date(
                current.year + (current.month == 12), current.month % 12 + 1, 1
            )
            finish = min(upper, next_month - timedelta(days=1))
        label = (
            current.strftime("%d.%m")
            if granularity != "month"
            else current.strftime("%m.%Y")
        )
        full_label = (
            current.strftime("%d.%m.%Y")
            if current == finish
            else f"С {current:%d.%m.%Y} по {finish:%d.%m.%Y}"
        )
        points.append(
            {
                "start": current,
                "end": finish,
                "label": label,
                "full_label": full_label,
                "detected": sum(
                    count for day, count in counts.items() if current <= day <= finish
                ),
            }
        )
        if finish == upper:
            break
        current = finish + timedelta(days=1)
    return {
        "granularity": granularity,
        "title": titles[granularity] if len(points) > 1 else "Выявление рисков",
        "points": points,
    }


def analysis(items: list[dict], start: date | None, end: date | None) -> dict:
    by_type: dict[str, dict] = {}
    by_owner: dict[int | None, dict] = {}
    for item in items:
        key = item["type_name"]
        row = by_type.setdefault(
            key,
            {
                "name": key,
                "total": 0,
                "open": 0,
                "critical": 0,
                "closed": 0,
                "recommendation": item.get("recommendation", ""),
            },
        )
        row["total"] += 1
        row["open"] += item["status"] in OPEN
        row["critical"] += item["status"] in OPEN and item["severity"] == "critical"
        row["closed"] += item["status"] == "closed"
        owner = item.get("responsible_name") or "Не назначен"
        person = by_owner.setdefault(
            item.get("responsible_id"),
            {
                "user_id": item.get("responsible_id"),
                "name": owner,
                "total": 0,
                "closed": 0,
                "in_progress": 0,
                "open": 0,
                "critical": 0,
            },
        )
        person["total"] += 1
        person["closed"] += item["status"] == "closed"
        person["in_progress"] += item["status"] == "in_progress"
        person["open"] += item["status"] in OPEN
        person["critical"] += item["status"] in OPEN and item["severity"] == "critical"
    severity_counts = Counter(row["severity"] for row in items)
    status_counts = Counter(row["status"] for row in items)
    timeline = risk_timeline(items, start, end)
    return {
        "date_from": start,
        "date_to": end,
        "charts": {
            "timeline": timeline,
            "severities": [
                {"key": key, "label": label, "value": severity_counts[key]}
                for key, label in SEVERITIES.items()
            ],
            "statuses": [
                {"key": key, "label": label, "value": status_counts[key]}
                for key, label in STATUSES.items()
            ],
            "types": [
                {"key": row["name"], "label": row["name"], "value": row["total"]}
                for row in sorted(
                    by_type.values(), key=lambda row: (-row["total"], row["name"])
                )[:7]
            ],
        },
        "totals": {
            "open": sum(r["status"] in OPEN for r in items),
            "critical": sum(
                r["status"] in OPEN and r["severity"] == "critical" for r in items
            ),
            "unassigned": sum(
                r["status"] in OPEN and not r["responsible_id"] for r in items
            ),
            "closed": sum(r["status"] == "closed" for r in items),
        },
        "types": sorted(
            by_type.values(), key=lambda r: (-r["critical"], -r["open"], r["name"])
        ),
        "owners": sorted(
            by_owner.values(), key=lambda r: (r["user_id"] is None, name_sort_key(r["name"], r["user_id"] or 0))
        ),
    }


def report_sections(data: dict) -> list[dict]:
    totals, charts = data["totals"], data["charts"]
    timeline = charts["timeline"]
    return [
        {
            "title": "Реагирование на риски",
            "headers": ["Показатель", "Количество"],
            "rows": [
                ["Открытые риски", totals["open"]],
                ["Критические открытые", totals["critical"]],
                ["Без ответственного", totals["unassigned"]],
                ["Закрытые риски", totals["closed"]],
            ],
        },
        {
            "title": "Приоритеты по типам",
            "headers": [
                "Тип риска",
                "Открыто",
                "Критических",
                "Закрыто",
                "Рекомендуемое действие",
            ],
            "rows": [
                [r["name"], r["open"], r["critical"], r["closed"], r["recommendation"]]
                for r in data["types"]
            ],
        },
        {
            "title": "Ответственные",
            "headers": ["Ответственный", "Всего", "Открыто", "В работе", "Критических открыто", "Закрыто"],
            "rows": [[r["name"], r["total"], r["open"], r["in_progress"], r["critical"], r["closed"]] for r in data["owners"]],
        },
        {
            "title": timeline["title"],
            "headers": ["Период выявления", "Выявлено рисков"],
            "rows": [
                [row["full_label"], row["detected"]] for row in timeline["points"]
            ],
            "chart": (
                {
                    "type": "line",
                    "columns": [1],
                    "unit": "рисков",
                    "integer": True,
                    "labels": [row["label"] for row in timeline["points"]],
                }
                if len(timeline["points"]) > 1
                else None
            ),
        },
        *[
            {
                "title": title,
                "headers": ["Категория", "Количество рисков"],
                "rows": [[row["label"], row["value"]] for row in charts[key]],
                "chart": {"type": kind, "columns": [1], "unit": "рисков"},
            }
            for key, title, kind in (
                ("severities", "Критичность рисков", "doughnut"),
                ("statuses", "Состояния рисков", "doughnut"),
                ("types", "Наиболее частые типы рисков", "bar"),
            )
        ],
    ]


def delivery_impact(db, project_id: int) -> dict:

    from sqlalchemy import select
    from app.common.models import User
    from app.modules.time_tracking.models import Task
    from app.modules.risk_management.models import Risk
    from .severity import risk_severity
    risks = list(db.scalars(select(Risk).where(Risk.project_id == project_id, Risk.status.in_(OPEN))))
    tasks = {t.task_id: t for t in db.scalars(select(Task).where(Task.project_id == project_id))}
    ids = {uid for risk in risks for uid in (risk.responsible_id, risk.subject_user_id) if uid}
    names = {u.user_id: u.full_name for u in db.scalars(select(User).where(User.user_id.in_(ids)))}
    zones = {}
    risky_tasks, risky_milestones, overdue_tasks = set(), set(), set()
    for risk in risks:
        task = tasks.get(risk.task_id)
        if task and task.status not in ("done", "cancelled") and not risk.is_cause_resolved:
            (risky_milestones if task.is_milestone else risky_tasks).add(task.task_id)
            if task.due_date < today():
                overdue_tasks.add(task.task_id)
        key = ("task", task.task_id) if task else ("person", risk.subject_user_id) if risk.subject_user_id else ("project", project_id)
        zone = zones.setdefault(key, {"target": task.name if task else names.get(risk.subject_user_id, "Проект в целом"),
            "task_id": task.task_id if task else None, "risk_id": risk.risk_id,
            "deadline": task.due_date if task else None, "open": 0, "critical": 0,
            "unassigned": 0, "overdue_actions": 0, "resolved": 0,
            "owners": set(), "recommendations": set(), "is_milestone": bool(task and task.is_milestone)})
        zone["open"] += 1
        zone["critical"] += risk_severity(risk) == "critical"
        zone["unassigned"] += risk.responsible_id is None
        zone["resolved"] += risk.is_cause_resolved
        zone["overdue_actions"] += sum(a.execution_state != "done" and a.due_date is not None and a.due_date < today() for a in risk.actions)
        if risk.responsible_id:
            zone["owners"].add(names.get(risk.responsible_id, "Не назначен"))
        if risk.risk_type.recommendation and not risk.is_cause_resolved:
            zone["recommendations"].add(risk.risk_type.recommendation)
    rows = []
    for zone in zones.values():
        decisions = []
        if zone["unassigned"]:
            decisions.append("Назначить ответственного")
        if zone["overdue_actions"]:
            decisions.append("Проверить просроченные меры реагирования")
        if zone["resolved"]:
            decisions.append("Проверить закрытие рисков с устранённым основанием")
        decisions.extend(sorted(zone.pop("recommendations")))
        rows.append({**zone, "owners": ", ".join(sorted(zone["owners"], key=name_sort_key)) or "Не назначен",
                     "decision": "; ".join(decisions) or "Уточнить план реагирования"})
    return {"tasks": len(risky_tasks), "milestones": len(risky_milestones), "overdue": len(overdue_tasks),
            "unassigned": sum(r.responsible_id is None for r in risks),
            "zones": sorted(rows, key=lambda z: (-z["critical"], z["deadline"] or date.max, z["target"]))}
