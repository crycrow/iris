from app.core.clock import today as app_today

"""Заполнение и чтение производственного календаря проекта."""
import json
from datetime import date, timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.common.models import Project, SystemSetting
from app.modules.time_tracking.models import Calendar


def settings_values(db: Session) -> dict[str, str]:
    return {r.setting_key: r.setting_value for r in db.scalars(select(SystemSetting))}


def ensure_calendar(db: Session, project: Project, as_of: date | None = None) -> None:

    current = as_of or app_today()
    values = settings_values(db)
    holidays_2026 = [f"2026-01-{d:02d}" for d in range(1, 10)] + [
        "2026-02-23",
        "2026-03-08",
        "2026-03-09",
        "2026-05-01",
        "2026-05-09",
        "2026-05-11",
        "2026-06-12",
        "2026-11-04",
        "2026-12-31",
    ]
    holidays = set(
        json.loads(values.get("calendar_holidays", json.dumps(holidays_2026)))
    )
    shortened = set(
        json.loads(
            values.get(
                "calendar_shortened",
                '["2026-04-30","2026-05-08","2026-06-11","2026-11-03"]',
            )
        )
    )
    overrides = json.loads(values.get("calendar_overrides", "{}"))
    daily = float(values.get("daily_hours", "8"))
    start = date(min(project.start_date.year, (current - timedelta(days=6)).year), 1, 1)
    end = date(max(project.end_date.year, (current + timedelta(days=32)).year), 12, 31)
    existing = set(
        db.scalars(
            select(Calendar.calendar_date).where(
                Calendar.project_id == project.project_id
            )
        )
    )
    rows = []
    while start <= end:
        if start not in existing:
            key = start.isoformat()
            hours = (
                0
                if start.weekday() > 4 or key in holidays
                else daily - 1 if key in shortened else daily
            )
            rows.append(
                Calendar(
                    project_id=project.project_id,
                    calendar_date=start,
                    working_hours=overrides.get(key, hours),
                )
            )
        start += timedelta(days=1)
    db.add_all(rows)
    db.flush()


def read_calendar(db: Session, project_id: int) -> dict[date, float]:
    return {
        r.calendar_date: float(r.working_hours)
        for r in db.scalars(select(Calendar).where(Calendar.project_id == project_id))
    }
