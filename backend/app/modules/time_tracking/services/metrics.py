from dataclasses import dataclass, asdict
from datetime import date, timedelta
from math import ceil
from collections.abc import Iterable, Mapping


@dataclass(frozen=True)
class EVM:
    bac: float
    pv: float
    ev: float
    ac: float

    def derived(self) -> dict[str, float | None]:
        spi = self.ev / self.pv if self.pv else None
        cpi = self.ev / self.ac if self.ac else None
        eac = self.bac / cpi if cpi else self.ac + self.bac - self.ev
        return {
            **asdict(self),
            "sv": self.ev - self.pv,
            "cv": self.ev - self.ac,
            "spi": spi,
            "cpi": cpi,
            "eac": eac,
            "etc": eac - self.ac,
            "vac": self.bac - eac,
        }


def working_days(calendar: Mapping[date, float], start: date, end: date) -> int:

    days = 0
    while start <= end:
        if start not in calendar:
            raise ValueError(f"В календаре отсутствует дата {start.isoformat()}")
        days += calendar[start] > 0
        start += timedelta(days=1)
    return days


def progress(status: str, progress_pct: int) -> float:
    return (
        1.0
        if status == "done"
        else 0.0 if status in ("backlog", "todo") else progress_pct / 100
    )


def task_evm(
    bac: float,
    start: date,
    due: date,
    status: str,
    progress_pct: int,
    entries: Iterable[tuple[date, float]],
    calendar: Mapping[date, float],
    as_of: date,
    is_milestone: bool = False,
) -> EVM:
    if status == "cancelled" or is_milestone:
        return EVM(0, 0, 0, 0)
    n = working_days(calendar, start, due)
    elapsed = working_days(calendar, start, min(as_of, due)) if as_of >= start else 0
    pv = bac if due <= as_of else bac * elapsed / n if n else 0
    return EVM(
        bac,
        pv,
        bac * progress(status, progress_pct),
        sum(h for d, h in entries if d <= as_of),
    )


def aggregate(values: Iterable[EVM]) -> EVM:
    rows = list(values)
    return EVM(
        *(sum(getattr(row, name) for row in rows) for name in ("bac", "pv", "ev", "ac"))
    )


def overdue_days(
    calendar: Mapping[date, float], due: date, as_of: date, completed: bool = False
) -> int:
    return (
        0
        if completed or as_of <= due
        else working_days(calendar, due + timedelta(days=1), as_of)
    )


def days_without_entries(
    calendar: Mapping[date, float],
    start: date,
    last_entry: date | None,
    as_of: date,
    status: str,
) -> int:
    if status not in ("dev", "review", "testing"):
        return 0
    return working_days(calendar, (last_entry or start) + timedelta(days=1), as_of)


def forecast_delay(
    evm: EVM, duration: int, overdue: int = 0, completed: bool = False
) -> int | None:
    if completed:
        return 0
    spi = evm.derived()["spi"]
    estimate = ceil(duration / spi) - duration if spi and evm.ev > 0 else None
    return max(estimate or 0, overdue) if overdue else estimate


def utilization(hours: float, days: int, daily_hours: float = 8) -> float | None:
    return hours / (daily_hours * days) * 100 if daily_hours > 0 and days > 0 else None


def remaining_work(assigned_hours: float, progress_fraction: float) -> float:
    return assigned_hours * (1 - progress_fraction)


def participant_share(remaining: float, total: float) -> float:
    return remaining / total * 100 if total else 0


def team_capacity(
    days_left: int, other_project_hours: Iterable[float], daily_hours: float = 8
) -> float:
    return sum(max(0, daily_hours * days_left - other) for other in other_project_hours)
