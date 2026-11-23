from datetime import date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator


class TrimmedInput(BaseModel):
    @field_validator(
        "login",
        "full_name",
        "name",
        "email",
        "job_title",
        mode="before",
        check_fields=False,
    )
    @classmethod
    def trim_names(cls, value):
        return value.strip() if isinstance(value, str) else value


Role = Literal["admin", "manager", "employee"]


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    user_id: int
    full_name: str
    login: str
    role: Role
    email: str
    job_title: str
    is_blocked: bool


class LoginIn(TrimmedInput):
    login: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1024)


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UserCreate(TrimmedInput):
    login: str = Field(min_length=1, max_length=100)
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=1024)
    role: Role = "employee"
    job_title: str = ""
    email: str = ""


class UserUpdate(TrimmedInput):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    password: str | None = Field(default=None, min_length=8, max_length=1024)
    role: Role | None = None
    job_title: str | None = None
    email: str | None = None
    is_blocked: bool | None = None


class ProjectIn(TrimmedInput):
    name: str = Field(min_length=1, max_length=250)
    description: str = ""
    start_date: date
    end_date: date
    planned_hours: float = Field(default=0, ge=0, allow_inf_nan=False)
    status: Literal["planned", "active", "completed", "cancelled"] = "planned"
    manager_id: int | None = Field(default=None, gt=0)
    member_ids: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_dates(self):
        if self.end_date < self.start_date:
            raise ValueError("Окончание проекта раньше начала")
        return self


class MembersIn(BaseModel):
    user_ids: list[int]


class SettingIn(BaseModel):
    setting_value: str


class Ok(BaseModel):
    ok: bool = True
