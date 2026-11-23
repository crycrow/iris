import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select
from app.core.database import SessionLocal
from app.core.config import settings
from app.common.models import SystemSetting

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler(timezone=settings.timezone)
WEEKDAYS = {
    name: index
    for index, name in enumerate(("mon", "tue", "wed", "thu", "fri", "sat", "sun"))
}


def grace_seconds(hour: int, minute: int, second: int = 0) -> int:

    return max(1, min(3600, (24 * 60 - hour * 60 - minute) * 60 - second - 1))


def scheduled_date(now: datetime, day: str, hour: int, minute: int, second: int = 0) -> date | None:

    local = now.astimezone(ZoneInfo(settings.timezone))
    scheduled = (local - timedelta(days=(local.weekday() - WEEKDAYS[day]) % 7)).replace(
        hour=hour, minute=minute, second=second, microsecond=0
    )
    if scheduled > local:
        scheduled -= timedelta(weeks=1)
    if scheduled.date() != local.date() or (
        local - scheduled
    ).total_seconds() > grace_seconds(hour, minute, second):
        return None
    return scheduled.date()


def weekly_analysis(day: str = "sun", hour: int = 23, minute: int = 55, second: int = 0) -> None:
    from app.core.integration import analyze

    now = datetime.now(ZoneInfo(settings.timezone))
    as_of = scheduled_date(now, day, hour, minute, second)
    if as_of is None:
        logger.warning(
            "Плановый анализ пропущен после допустимого окна. Время %s, расписание %s %02d:%02d:%02d. Срез прошлой недели не изменён",
            now.isoformat(),
            day,
            hour,
            minute,
            second,
        )
        return
    with SessionLocal.begin() as db:
        analyze(db, as_of)


def reschedule() -> None:
    with SessionLocal() as db:
        values = {
            s.setting_key: s.setting_value for s in db.scalars(select(SystemSetting))
        }
    day = values.get("scheduler_day", "sun")
    hour = int(values.get("scheduler_hour", "23"))
    minute = int(values.get("scheduler_minute", "55"))
    second = int(values.get("scheduler_second", "0"))
    scheduler.add_job(
        weekly_analysis,
        "cron",
        id="weekly_analysis",
        replace_existing=True,
        day_of_week=day,
        hour=hour,
        minute=minute,
        second=second,
        kwargs={"day": day, "hour": hour, "minute": minute, "second": second},
        max_instances=1,
        coalesce=True,
        misfire_grace_time=grace_seconds(hour, minute, second),
    )


def start() -> None:
    if settings.scheduler_enabled and not scheduler.running:
        reschedule()
        scheduler.start()


def stop() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=True)
