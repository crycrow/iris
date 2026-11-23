import math
from fastapi import HTTPException
from app.modules.risk_management.models import RiskType
from ..catalog import parameters
from .base import compare, consecutive, finding, value

METRICS = {
    "progress_pct": ("Готовность работ", "%"),
    "schedule_pct": ("Выполнение плана к дате анализа", "%"),
    "efficiency_pct": ("Эффективность трудозатрат", "%"),
    "ac": ("Фактические трудозатраты", "ч"),
    "delta_t": ("Просрочка", "раб. дн."),
    "t_safe": ("Период без списаний", "раб. дн."),
    "s": ("Прогноз сдвига срока", "раб. дн."),
    "capacity_gap": ("Недостаток доступного времени", "ч"),
    "w": ("Оставшиеся работы", "ч"),
    "u_plan": ("Плановая загрузка в текущем месяце", "%"),
    "u_plan_next": ("Плановая загрузка в следующем месяце", "%"),
    "u_fact": ("Фактическая загрузка за неделю", "%"),
}
ALLOWED = {
    "task": {
        "progress_pct",
        "schedule_pct",
        "efficiency_pct",
        "ac",
        "delta_t",
        "t_safe",
    },
    "project": {
        "progress_pct",
        "schedule_pct",
        "efficiency_pct",
        "ac",
        "s",
        "capacity_gap",
        "w",
    },
    "employee": {"u_plan", "u_plan_next", "u_fact"},
}


def validate(data: dict) -> None:
    if (
        data.get("object_kind") not in ALLOWED
        or data.get("metric") not in ALLOWED[data["object_kind"]]
    ):
        raise HTTPException(
            422, "Выберите показатель, доступный для выбранного объекта"
        )
    threshold = data.get("threshold")
    if (
        threshold is None
        or not math.isfinite(threshold)
        or not 0 <= threshold < 100000000
    ):
        raise HTTPException(
            422, "Порог должен быть неотрицательным числом меньше 100 миллионов"
        )
    if data["metric"] == "progress_pct" and threshold > 100:
        raise HTTPException(
            422, "Готовность должна находиться в пределах от 0 до 100 процентов"
        )
    params = data.get("params", {})
    if not isinstance(params, dict):
        raise HTTPException(422, "Укажите параметры подтверждения условия")
    weeks = params.get("consecutive_weeks")
    if (
        set(params) != {"consecutive_weeks"}
        or weeks is None
        or not math.isfinite(weeks)
        or not 1 <= weeks <= 52
        or weeks != int(weeks)
    ):
        raise HTTPException(422, "Укажите число последовательных недель от 1 до 52")
    for key in ("name", "risk_group"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise HTTPException(422, "Название и группа риска не должны быть пустыми")


def measured_value(row: dict, metric: str) -> float | None:
    ratios = {
        "progress_pct": ("ev", "bac"),
        "schedule_pct": ("ev", "pv"),
        "efficiency_pct": ("ev", "ac"),
    }
    if metric in ratios:
        numerator, denominator = ratios[metric]
        total = row.get(denominator)
        amount = row.get(numerator)
        return (
            float(amount) / float(total) * 100 if total and amount is not None else None
        )
    if metric == "capacity_gap" and (row.get("w") is None or row.get("m") is None):
        return None
    return value(row, metric)


def evaluate(rt: RiskType, context: dict) -> list[dict]:
    result = []
    weeks = int(parameters(rt).get("consecutive_weeks", 1))
    for key, rows in context["histories"].items():
        project_id, task_id, user_id = key
        matches = (
            rt.object_kind == "task"
            and project_id is not None
            and task_id is not None
            and user_id is None
            or rt.object_kind == "project"
            and project_id is not None
            and task_id is None
            and user_id is None
            or rt.object_kind == "employee"
            and project_id is None
            and task_id is None
            and user_id is not None
        )
        if not matches or not rows:
            continue
        task = context["tasks"].get(task_id)
        if task and (
            task.status == "cancelled"
            or task.status == "done"
            and rt.metric in {"delta_t", "t_safe", "schedule_pct", "progress_pct"}
        ):
            continue
        if rt.object_kind == "employee" and user_id not in context["active_users"]:
            continue
        if not consecutive(
            rows,
            weeks,
            context["week"],
            lambda row: compare(
                measured_value(row, rt.metric), rt.condition_op, float(rt.threshold)
            ),
        ):
            continue
        measured = measured_value(rows[0], rt.metric)
        if measured is None:
            continue
        label, unit = METRICS[rt.metric]
        result.append(
            finding(rt, key, measured, f"{label} составляет {measured:.2f} {unit}")
        )
    return result
