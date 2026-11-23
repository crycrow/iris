from datetime import date, datetime, timezone
from decimal import Decimal
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    extract,
)
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class Calendar(Base):
    __tablename__ = "calendars"
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.project_id", ondelete="RESTRICT"), primary_key=True
    )
    calendar_date: Mapped[date] = mapped_column(Date, primary_key=True)
    working_hours: Mapped[Decimal] = mapped_column(Numeric(4, 2))
    __table_args__ = (CheckConstraint("working_hours >= 0 AND working_hours <= 24"),)


class Release(Base):
    __tablename__ = "releases"
    release_id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.project_id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    release_date: Mapped[date] = mapped_column(Date)
    description: Mapped[str] = mapped_column(Text, default="")


class Task(Base):
    __tablename__ = "tasks"
    task_id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.project_id", ondelete="RESTRICT"), index=True
    )
    release_id: Mapped[int | None] = mapped_column(
        ForeignKey("releases.release_id", ondelete="RESTRICT")
    )
    parent_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.task_id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    is_milestone: Mapped[bool] = mapped_column(Boolean, default=False)
    start_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date)
    progress_pct: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="backlog")
    __table_args__ = (
        CheckConstraint("progress_pct BETWEEN 0 AND 100"),
        CheckConstraint("due_date >= start_date"),
        CheckConstraint("NOT is_milestone OR start_date = due_date"),
        CheckConstraint(
            "status IN ('backlog','todo','dev','review','testing','release_wait','done','cancelled')"
        ),
        CheckConstraint("status != 'done' OR progress_pct = 100"),
        CheckConstraint("status NOT IN ('backlog','todo') OR progress_pct = 0"),
    )


class TaskAssignment(Base):
    __tablename__ = "task_assignments"
    assignment_id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.task_id", ondelete="RESTRICT"), index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="RESTRICT"), index=True
    )
    __table_args__ = (UniqueConstraint("task_id", "user_id"),)


class ResourcePlan(Base):
    __tablename__ = "resource_plan"
    assignment_id: Mapped[int] = mapped_column(
        ForeignKey("task_assignments.assignment_id", ondelete="CASCADE"),
        primary_key=True,
    )
    plan_month: Mapped[date] = mapped_column(Date, primary_key=True)
    planned_hours: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0)
    __table_args__ = (
        CheckConstraint("planned_hours >= 0"),
        CheckConstraint(extract("day", plan_month) == 1),
    )


class TimeEntry(Base):
    __tablename__ = "time_entries"
    entry_id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="RESTRICT"), index=True
    )
    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.task_id", ondelete="RESTRICT")
    )
    work_date: Mapped[date] = mapped_column(Date)
    hours: Mapped[Decimal] = mapped_column(Numeric(4, 2))
    comment: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (
        CheckConstraint("hours >= 0.5 AND hours <= 24"),
        Index("ix_time_entries_task_date", "task_id", "work_date"),
    )


class TaskActivity(Base):
    __tablename__ = "task_activity"
    activity_id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.task_id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.user_id", ondelete="RESTRICT")
    )
    change_type: Mapped[str] = mapped_column(String(40))
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class MetricSnapshot(Base):
    __tablename__ = "metric_snapshots"
    snapshot_id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.project_id", ondelete="RESTRICT")
    )
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.task_id", ondelete="RESTRICT")
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.user_id", ondelete="RESTRICT")
    )
    week_start: Mapped[date] = mapped_column(Date)
    bac: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=0)
    pv: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=0)
    ev: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=0)
    ac: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=0)
    s: Mapped[float | None] = mapped_column(Numeric(14, 4))
    delta_t: Mapped[int] = mapped_column(Integer, default=0)
    t_safe: Mapped[int] = mapped_column(Integer, default=0)
    w: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=0)
    m: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=0)
    u_plan: Mapped[float | None] = mapped_column(Numeric(14, 4))
    u_plan_next: Mapped[float | None] = mapped_column(Numeric(14, 4))
    u_fact: Mapped[float | None] = mapped_column(Numeric(14, 4))
    k: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=0)
    __table_args__ = (
        Index("ix_snapshots_project_week", "project_id", "week_start"),
        CheckConstraint("project_id IS NOT NULL OR user_id IS NOT NULL"),
        Index(
            "uq_snapshot_scope_week",
            func.coalesce(project_id, 0),
            func.coalesce(task_id, 0),
            func.coalesce(user_id, 0),
            week_start,
            unique=True,
        ),
    )
