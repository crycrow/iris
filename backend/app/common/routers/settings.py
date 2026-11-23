import json
import math
import re
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.common.models import User, SystemSetting
from app.common.permissions import require_roles
from app.common.schemas import SettingIn

EDITABLE_SETTINGS = {
    "token_minutes",
    "scheduler_day",
    "scheduler_hour",
    "scheduler_minute",
    "scheduler_second",
    "scheduler_time",
}

router = APIRouter(prefix="/api/settings", tags=["Настройки"])


def calendar_date(value: object) -> None:
    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
        raise ValueError("Дата должна иметь формат ГГГГ-ММ-ДД")


def validate_setting(key: str, value: str) -> str:

    value = value.strip()
    if key == "scheduler_time":
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d", value):
            raise ValueError("Время должно иметь формат ЧЧ:ММ:СС")
        return value
    if key in ("daily_hours", "weekly_hours", "token_minutes", "p_min", "k"):
        number = float(value)
        if not math.isfinite(number) or number <= 0:
            raise ValueError("Ожидается положительное конечное число")
        if key in ("token_minutes", "k"):
            if not number.is_integer():
                raise ValueError("Ожидается целое число")
            value = str(int(number))
        if key == "daily_hours" and not 1 <= number <= 24:
            raise ValueError("Норма дня должна быть от 1 до 24 часов")
        if key == "weekly_hours" and number > 168:
            raise ValueError("Норма недели не может превышать 168 часов")
        if key == "p_min" and number > 100:
            raise ValueError("Процент не может превышать 100")
    if key in ("calendar_holidays", "calendar_shortened"):
        dates = json.loads(value)
        if not isinstance(dates, list):
            raise ValueError("Ожидается список дат")
        for item in dates:
            calendar_date(item)
        value = json.dumps(sorted(set(dates)), ensure_ascii=False)
    elif key == "calendar_overrides":
        overrides = json.loads(value)
        if not isinstance(overrides, dict):
            raise ValueError("Ожидается объект с датами и числом часов")
        for day, hours in overrides.items():
            calendar_date(day)
            if (
                isinstance(hours, bool)
                or not isinstance(hours, (int, float))
                or not math.isfinite(hours)
                or not 0 <= hours <= 24
            ):
                raise ValueError("Число часов календаря должно быть от нуля до 24")
        value = json.dumps(overrides, ensure_ascii=False)
    if key == "scheduler_hour" and not 0 <= int(value) <= 23:
        raise ValueError("Час должен быть от нуля до 23")
    if key == "scheduler_minute" and not 0 <= int(value) <= 59:
        raise ValueError("Минута должна быть от нуля до 59")
    if key == "scheduler_second" and not 0 <= int(value) <= 59:
        raise ValueError("Секунда должна быть от нуля до 59")
    if key == "scheduler_day" and value not in (
        "mon",
        "tue",
        "wed",
        "thu",
        "fri",
        "sat",
        "sun",
    ):
        raise ValueError("Некорректный день недели")
    return value


@router.get("")
def get_settings(
    user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)
):
    values = {s.setting_key: s for s in db.scalars(select(SystemSetting))}
    result = [
        {
            "setting_key": s.setting_key,
            "setting_value": s.setting_value,
            "description": s.description,
        }
        for key in ("token_minutes", "scheduler_day")
        if (s := values.get(key)) is not None
    ]
    parts = [int(values[key].setting_value) if key in values else default
             for key, default in (("scheduler_hour", 23), ("scheduler_minute", 55), ("scheduler_second", 0))]
    result.append({"setting_key": "scheduler_time", "setting_value": ":".join(f"{part:02d}" for part in parts),
                   "description": "Время еженедельного анализа по Москве"})
    return result


@router.put("/{key}")
def put_setting(
    key: str,
    body: SettingIn,
    user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    if key not in EDITABLE_SETTINGS:
        raise HTTPException(
            422, "Этот параметр не является пользовательской настройкой системы"
        )
    try:
        value = validate_setting(key, body.setting_value)
    except (ValueError, TypeError, OverflowError):
        raise HTTPException(422, "Некорректное значение настройки")
    if key == "scheduler_time":
        for part_key, part in zip(("scheduler_hour", "scheduler_minute", "scheduler_second"), value.split(":")):
            part_row = db.scalar(select(SystemSetting).where(SystemSetting.setting_key == part_key))
            if part_row is None:
                part_row = SystemSetting(setting_key=part_key, setting_value=str(int(part)))
                db.add(part_row)
            else:
                part_row.setting_value = str(int(part))
        db.commit()
        from app.core.scheduler import reschedule

        reschedule()
        return {"setting_key": key, "setting_value": value}
    row = db.scalar(select(SystemSetting).where(SystemSetting.setting_key == key))
    if not row:
        raise HTTPException(404, "Настройка не найдена")
    row.setting_value = value
    db.commit()
    if key.startswith("scheduler_"):
        from app.core.scheduler import reschedule

        reschedule()
    return {"setting_key": key, "setting_value": row.setting_value}
