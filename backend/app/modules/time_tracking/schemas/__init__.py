from datetime import date
from decimal import Decimal
from typing import Literal, Any
from pydantic import BaseModel, ConfigDict, Field, field_validator

TaskStatus = Literal[
    "backlog", "todo", "dev", "review", "testing", "release_wait", "done", "cancelled"
]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TaskCreate(Input):
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    start_date: date
    due_date: date
    parent_task_id: int | None = None
    release_id: int | None = None
    is_milestone: bool = False
    progress_pct: int = Field(default=0, ge=0, le=100)
    status: TaskStatus = "backlog"


class TaskUpdate(Input):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    start_date: date | None = None
    due_date: date | None = None
    parent_task_id: int | None = None
    release_id: int | None = None
    is_milestone: bool | None = None
    progress_pct: int | None = Field(default=None, ge=0, le=100)
    status: TaskStatus | None = None


class CommentCreate(Input):
    text: str = Field(min_length=1, max_length=10000)


class ReleaseCreate(Input):
    name: str = Field(min_length=1, max_length=255)
    release_date: date
    description: str = ""


class EntryCreate(Input):
    task_id: int
    work_date: date
    hours: Decimal = Field(ge=Decimal("0.5"), le=24, max_digits=4, decimal_places=2)
    comment: str = Field(default="", max_length=10000)


class PlanUpdate(Input):
    user_id: int
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    planned_hours: Decimal = Field(ge=0, max_digits=6, decimal_places=2)


class PlanUpdates(Input):
    updates: list[PlanUpdate] = Field(min_length=1)


class AssignmentItem(Input):
    task_id: int
    planned_hours: Decimal = Field(ge=0, max_digits=6, decimal_places=2)


class MonthAssignments(Input):
    user_id: int = Field(gt=0)
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    items: list[AssignmentItem] = Field(default_factory=list)
    remove_task_ids: list[int] = Field(default_factory=list)

    @field_validator("month")
    @classmethod
    def valid_month(cls, value: str) -> str:
        date.fromisoformat(value + "-01")
        return value


class Assignments(Input):
    user_id: int
    items: list[AssignmentItem] = Field(min_length=1)
    months: list[str] | None = None

    @field_validator("months")
    @classmethod
    def valid_months(cls, value: list[str] | None) -> list[str] | None:
        if value is not None:
            for month in value:
                date.fromisoformat(month + "-01")
        return value


class CalendarUpdate(Input):
    calendar_date: date
    working_hours: Decimal = Field(ge=0, le=24, decimal_places=2)


class Result(BaseModel):
    ok: bool = True


class Items(BaseModel):
    items: list[dict[str, Any]]


class TaskResult(BaseModel):
    task: dict[str, Any]
    assignments: list[dict[str, Any]]
    activity: list[dict[str, Any]]
