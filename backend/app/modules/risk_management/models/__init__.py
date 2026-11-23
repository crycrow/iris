from datetime import date, datetime, timezone
from decimal import Decimal
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RiskType(Base):
    __tablename__ = "risk_types"
    __table_args__ = (
        CheckConstraint("condition_op IN ('gt','gte','lt','lte')"),
        CheckConstraint("severity IN ('medium','high','critical')"),
    )
    risk_type_id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(250))
    description: Mapped[str] = mapped_column(Text, default="")
    risk_group: Mapped[str] = mapped_column(String(100))
    object_kind: Mapped[str | None] = mapped_column(String(20))
    metric: Mapped[str] = mapped_column(String(64))
    condition_op: Mapped[str] = mapped_column(String(4))
    threshold: Mapped[Decimal] = mapped_column(Numeric(14, 6))
    severity: Mapped[str] = mapped_column(String(20), default="medium")
    recommendation: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    params: Mapped[list["RiskTypeParam"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def rule_code(self) -> str:
        return self.code.split(":")[1] if self.code.startswith("custom:") else self.code


class RiskTypeParam(Base):
    __tablename__ = "risk_type_params"
    __table_args__ = (UniqueConstraint("risk_type_id", "param_name"),)
    param_id: Mapped[int] = mapped_column(primary_key=True)
    risk_type_id: Mapped[int] = mapped_column(
        ForeignKey("risk_types.risk_type_id", ondelete="CASCADE")
    )
    param_name: Mapped[str] = mapped_column(String(64))
    param_value: Mapped[Decimal] = mapped_column(Numeric(14, 6))


class Risk(Base):
    __tablename__ = "risks"
    __table_args__ = (
        CheckConstraint(
            "status IN ('new','reviewing','in_progress','closed','rejected')"
        ),
    )
    risk_id: Mapped[int] = mapped_column(primary_key=True)
    risk_type_id: Mapped[int] = mapped_column(
        ForeignKey("risk_types.risk_type_id", ondelete="RESTRICT")
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.project_id", ondelete="RESTRICT"), index=True
    )
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.task_id", ondelete="RESTRICT")
    )
    responsible_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.user_id", ondelete="RESTRICT")
    )
    subject_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.user_id", ondelete="RESTRICT")
    )
    measured_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="new")
    is_viewed: Mapped[bool] = mapped_column(Boolean, default=False)
    is_cause_resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    risk_type: Mapped[RiskType] = relationship(lazy="joined")
    events: Mapped[list["RiskEvent"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="RiskEvent.event_id"
    )
    actions: Mapped[list["RiskAction"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )


Index(
    "uq_open_risk_object",
    Risk.risk_type_id,
    func.coalesce(Risk.project_id, 0),
    func.coalesce(Risk.task_id, 0),
    func.coalesce(Risk.subject_user_id, 0),
    unique=True,
    postgresql_where=text("status IN ('new','reviewing','in_progress')"),
    sqlite_where=text("status IN ('new','reviewing','in_progress')"),
)


class RiskEvent(Base):
    __tablename__ = "risk_events"
    event_id: Mapped[int] = mapped_column(primary_key=True)
    risk_id: Mapped[int] = mapped_column(
        ForeignKey("risks.risk_id", ondelete="CASCADE"), index=True
    )
    initiator_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.user_id", ondelete="RESTRICT")
    )
    event_type: Mapped[str] = mapped_column(String(40))
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    details: Mapped[str] = mapped_column(Text)


class RiskAction(Base):
    __tablename__ = "risk_actions"
    __table_args__ = (
        CheckConstraint("execution_state IN ('planned','in_progress','done')"),
    )
    action_id: Mapped[int] = mapped_column(primary_key=True)
    risk_id: Mapped[int] = mapped_column(
        ForeignKey("risks.risk_id", ondelete="CASCADE"), index=True
    )
    description: Mapped[str] = mapped_column(Text)
    due_date: Mapped[date | None] = mapped_column(Date)
    execution_state: Mapped[str] = mapped_column(String(20), default="planned")

__all__ = ["RiskType", "RiskTypeParam", "Risk", "RiskEvent", "RiskAction"]
