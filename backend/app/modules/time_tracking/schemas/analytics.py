from datetime import date
from pydantic import BaseModel, Field


class MonthlyHours(BaseModel):
    month: date
    planned_hours: float
    actual_hours: float | None
    is_future: bool


class WeeklyMetrics(BaseModel):
    week_start: date
    bac: float
    pv: float
    ev: float
    ac: float
    sv: float
    cv: float
    spi: float | None
    cpi: float | None
    eac: float
    etc: float
    vac: float
    is_current_week: bool


class EmployeeHours(BaseModel):
    user_id: int
    full_name: str
    planned_hours: float
    actual_hours: float
    total_actual_hours: float = 0
    project_share_pct: float | None = None


class DailyHours(BaseModel):
    work_date: date
    planned_hours: float = 0
    actual_hours: float | None


class TaskHours(BaseModel):
    task_id: int | None = None
    name: str
    actual_hours: float
    share_pct: float


class HourTotals(BaseModel):
    planned_hours: float = 0
    actual_hours: float = 0


class ProjectAnalytics(BaseModel):
    project_id: int
    as_of: date
    date_from: date
    date_to: date
    chart_granularity: str = "month"
    monthly: list[MonthlyHours] = Field(default_factory=list)
    weekly: list[WeeklyMetrics] = Field(default_factory=list)
    employees: list[EmployeeHours] = Field(default_factory=list)
    daily: list[DailyHours] = Field(default_factory=list)
    task_hours: list[TaskHours] = Field(default_factory=list)
    task_distribution: list[TaskHours] = Field(default_factory=list)
    totals: HourTotals = Field(default_factory=HourTotals)
    notes: list[str] = Field(default_factory=list)
