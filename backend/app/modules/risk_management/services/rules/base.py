from datetime import timedelta
from typing import Callable
from app.modules.risk_management.models import RiskType


def compare(value: float | None, op: str, threshold: float) -> bool:
    if value is None:
        return False
    return {
        "gt": lambda: value > threshold,
        "gte": lambda: value >= threshold,
        "lt": lambda: value < threshold,
        "lte": lambda: value <= threshold,
    }[op]()


def value(row: dict, metric: str) -> float | None:
    if metric in ("spi", "cpi"):
        denominator = float(row["pv" if metric == "spi" else "ac"] or 0)
        return float(row["ev"] or 0) / denominator if denominator else None
    if metric == "capacity_gap":
        return float(row["w"] or 0) - float(row["m"] or 0)
    item = row.get(metric)
    return float(item) if item is not None else None


def consecutive(
    rows: list[dict], count: int, week, predicate: Callable[[dict], bool]
) -> bool:

    return len(rows) >= count and all(
        row["week_start"] == week - timedelta(weeks=index) and predicate(row)
        for index, row in enumerate(rows[:count])
    )


def mature(row: dict, minimum: float) -> bool:
    return (
        bool(row["bac"]) and float(row["ev"] or 0) / float(row["bac"]) * 100 >= minimum
    )


def finding(rt: RiskType, key: tuple, measured: float, explanation: str) -> dict:
    return {
        "risk_type_id": rt.risk_type_id,
        "project_id": key[0],
        "task_id": key[1],
        "subject_user_id": key[2],
        "measured_value": measured,
        "description": f"{rt.name}. {explanation}. {rt.recommendation}",
    }
