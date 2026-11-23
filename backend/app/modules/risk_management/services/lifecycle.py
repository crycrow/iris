import json
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.modules.risk_management.models import Risk, RiskEvent

OPEN_STATUSES = ("new", "reviewing", "in_progress")
TRANSITIONS = {
    "new": ("reviewing", "rejected"),
    "reviewing": ("in_progress", "rejected"),
    "in_progress": ("reviewing", "closed"),
    "closed": (),
    "rejected": (),
}
STATUS_NAMES = {
    "new": "Новый",
    "reviewing": "На рассмотрении",
    "in_progress": "В работе",
    "closed": "Закрыт",
    "rejected": "Отклонён",
}


def add_event(
    db: Session,
    risk: Risk,
    initiator_id: int | None,
    event_type: str,
    details: str | dict,
) -> RiskEvent:
    event = RiskEvent(
        risk_id=risk.risk_id,
        initiator_id=initiator_id,
        event_type=event_type,
        details=(
            json.dumps(details, ensure_ascii=False)
            if isinstance(details, dict)
            else details
        ),
    )
    db.add(event)
    return event


def ensure_open(risk: Risk) -> None:
    if risk.status not in OPEN_STATUSES:
        raise HTTPException(409, "Закрытый или отклонённый риск нельзя изменять")


def transition(
    db: Session, risk: Risk, target: str, initiator_id: int | None, comment: str = ""
) -> None:
    if target not in TRANSITIONS.get(risk.status, ()):
        raise HTTPException(409, "Такой переход состояния риска запрещён")
    if target == "reviewing" and not risk.responsible_id:
        raise HTTPException(409, "Сначала назначьте ответственного")
    if target == "in_progress" and not risk.actions:
        raise HTTPException(409, "Сначала добавьте мероприятие")
    previous = risk.status
    risk.status = target
    if target in ("closed", "rejected"):
        risk.closed_at = datetime.now(timezone.utc)
    add_event(
        db,
        risk,
        initiator_id,
        "status",
        {"from": previous, "to": target, "comment": comment},
    )
