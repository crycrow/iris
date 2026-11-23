from datetime import date, datetime
from typing import Literal, Any
from pydantic import BaseModel, Field, ConfigDict

Severity = Literal["medium", "high", "critical"]
Status = Literal["new", "reviewing", "in_progress", "closed", "rejected"]


class RiskTypeUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=250)
    description: str | None = None
    risk_group: str | None = Field(None, min_length=1, max_length=100)
    object_kind: Literal["task", "project", "employee"] | None = None
    metric: str | None = None
    condition_op: Literal["gt", "gte", "lt", "lte"] | None = None
    threshold: float | None = None
    severity: Severity | None = None
    recommendation: str | None = None
    is_active: bool | None = None
    params: dict[str, float] | None = None


class RiskTypeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=250)
    description: str = ""
    risk_group: str = Field(min_length=1, max_length=100)
    object_kind: Literal["task", "project", "employee"]
    metric: str
    condition_op: Literal["gt", "gte", "lt", "lte"]
    threshold: float
    severity: Severity = "medium"
    recommendation: str = ""
    is_active: bool = True
    params: dict[str, float] = Field(default_factory=lambda: {"consecutive_weeks": 1.0})


class RiskCreate(BaseModel):
    risk_type_id: int
    project_id: int
    task_id: int | None = None
    subject_user_id: int | None = None
    description: str = Field(min_length=1)
    severity: Severity = "medium"
    responsible_id: int | None = None


class AssignmentIn(BaseModel):
    responsible_id: int


class StatusIn(BaseModel):
    status: Status
    comment: str = ""


class CommentIn(BaseModel):
    text: str = Field(min_length=1, max_length=10000)


class ActionIn(BaseModel):
    description: str = Field(min_length=1, max_length=10000)
    due_date: date | None = None
    execution_state: Literal["planned", "in_progress", "done"] = "planned"


class ActionUpdate(BaseModel):
    description: str | None = Field(None, min_length=1, max_length=10000)
    due_date: date | None = None
    execution_state: Literal["planned", "in_progress", "done"] | None = None


class RiskOut(BaseModel):
    risk_id: int
    risk_type_id: int
    type_name: str
    type_code: str
    risk_group: str
    project_id: int | None
    project_name: str | None = None
    task_id: int | None
    task_name: str | None = None
    subject_user_id: int | None
    subject_name: str | None = None
    responsible_id: int | None
    responsible_name: str | None = None
    measured_value: float | None
    threshold: float
    metric: str
    description: str
    recommendation: str
    severity: Severity
    status: Status
    status_name: str
    is_viewed: bool
    is_cause_resolved: bool
    detected_at: datetime
    closed_at: datetime | None
    can_manage: bool


class RiskList(BaseModel):
    items: list[RiskOut]
    counts: dict[str, Any]


class RiskTypeOut(BaseModel):
    risk_type_id: int
    code: str
    name: str
    description: str
    risk_group: str
    object_kind: str | None = None
    metric: str
    condition_op: str
    threshold: float
    severity: Severity
    recommendation: str
    is_active: bool
    params: dict[str, float]


class CatalogOut(BaseModel):
    items: list[RiskTypeOut]
    can_manage: bool
    custom_options: dict[str, Any] = Field(default_factory=dict)


class IdResult(BaseModel):
    risk_id: int


class OkResult(BaseModel):
    ok: bool = True


class ActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    action_id: int
    risk_id: int
    description: str
    due_date: date | None
    execution_state: str


class EventOut(BaseModel):
    event_id: int
    initiator_id: int | None
    initiator_name: str | None
    event_type: str
    event_at: datetime
    details: str


class RiskDetail(BaseModel):
    risk: RiskOut
    events: list[EventOut]
    actions: list[ActionOut]
    can_manage: bool
    allowed_transitions: list[str]
