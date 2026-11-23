from datetime import date, datetime, time, timezone
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.common.models import User, ProjectMember, Project
from app.common.services.people import name_sort_key
from app.common.permissions import (
    get_current_user,
    ensure_project_access,
    ensure_project_participant,
)
from app.common.exports.xlsx_base import make_xlsx, make_report_xlsx
from app.common.exports.pdf_base import make_pdf, make_report_pdf
from app.modules.risk_management.models import Risk, RiskType, RiskAction
from app.modules.risk_management.schemas import (
    RiskCreate,
    RiskList,
    RiskDetail,
    IdResult,
    OkResult,
    AssignmentIn,
    StatusIn,
    CommentIn,
    ActionIn,
    ActionUpdate,
    ActionOut,
)
from app.modules.risk_management.services.queries import (
    visibility,
    load_risk,
    serialize_risks,
    can_manage,
)
from app.modules.risk_management.services.lifecycle import (
    OPEN_STATUSES,
    TRANSITIONS,
    STATUS_NAMES,
    add_event,
    ensure_open,
    transition,
)
from app.modules.risk_management.services.readers import get_task
from app.modules.risk_management.services.reporting import (
    analysis,
    analysis_period,
    report_sections,
    STATUSES,
    SEVERITIES,
)

router = APIRouter(tags=["Реестр рисков"])


def filtered(
    db: Session,
    user: User,
    project_id: int | None = None,
    status: str | None = None,
    severity: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    risk_type_id: int | None = None,
    unviewed: bool = False,
    object_search: str = "",
) -> list[dict]:
    query = select(Risk).where(visibility(user))
    if project_id is not None:
        ensure_project_access(db, user, project_id)
        query = query.where(Risk.project_id == project_id)
    if status:
        query = query.where(Risk.status == status)
    if risk_type_id:
        query = query.where(Risk.risk_type_id == risk_type_id)
    if date_from:
        query = query.where(
            Risk.detected_at
            >= datetime.combine(date_from, time.min, tzinfo=timezone.utc)
        )
    if date_to:
        query = query.where(
            Risk.detected_at <= datetime.combine(date_to, time.max, tzinfo=timezone.utc)
        )
    if unviewed:
        query = query.where(Risk.is_viewed.is_(False), Risk.status.in_(OPEN_STATUSES))
    items = serialize_risks(
        db, user, list(db.scalars(query.order_by(Risk.detected_at.desc())))
    )
    terms = object_search.casefold().replace("ё", "е").split()
    return sorted([
        r for r in items
        if (not severity or r["severity"] == severity)
        and all(term in " ".join((r.get("project_name") or "", r.get("subject_name") or ""))
                .casefold().replace("ё", "е") for term in terms)
    ], key=lambda r: (name_sort_key(r.get("subject_name") or r.get("responsible_name") or "Яя"), r["risk_id"]))


@router.get("/api/risks", response_model=RiskList)
def list_risks(
    project_id: int | None = None,
    status: str | None = None,
    severity: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    risk_type_id: int | None = None,
    unviewed: bool = False,
    object_search: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    items = filtered(
        db,
        user,
        project_id,
        status,
        severity,
        date_from,
        date_to,
        risk_type_id,
        unviewed,
        object_search,
    )
    return {
        "items": items,
        "counts": {
            "total": len(items),
            "unviewed": sum(
                not r["is_viewed"] and r["status"] in OPEN_STATUSES for r in items
            ),
            "by_status": [
                {"status": s, "name": label, "c": sum(r["status"] == s for r in items)}
                for s, label in STATUS_NAMES.items()
            ],
        },
    }


@router.get("/api/risks/export.{format}")
def export_risks(
    format: str,
    project_id: int | None = None,
    status: str | None = None,
    severity: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    unviewed: bool = False,
    risk_type_id: int | None = None,
    object_search: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    if user.role not in ("admin", "manager"):
        raise HTTPException(
            403, "Отчёты доступны руководителям проектов и администраторам"
        )
    items = filtered(
        db,
        user,
        project_id,
        status,
        severity,
        date_from,
        date_to,
        risk_type_id,
        unviewed,
        object_search,
    )
    headers = [
        "Тип риска",
        "Проект",
        "Задача",
        "Сотрудник",
        "Критичность",
        "Статус",
        "Ответственный",
        "Описание",
    ]
    levels = {"medium": "Средняя", "high": "Высокая", "critical": "Критическая"}
    rows = [
        [
            r["type_name"],
            r["project_name"] or "Общая загрузка",
            r.get("task_name") or "",
            r.get("subject_name") or "",
            levels[r["severity"]],
            r["status_name"],
            r.get("responsible_name") or "Не назначен",
            r["description"],
        ]
        for r in items
    ]
    if format == "xlsx":
        return Response(
            make_xlsx("Реестр рисков", headers, rows),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="risks.xlsx"'},
        )
    if format == "pdf":
        return Response(
            make_pdf("Реестр рисков", headers, rows),
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="risks.pdf"'},
        )
    raise HTTPException(422, "Доступны форматы xlsx и pdf")


@router.get("/api/reports/risks")
def risk_analysis(
    project_id: int | None = None,
    status: str | None = None,
    severity: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    if user.role not in ("admin", "manager"):
        raise HTTPException(
            403, "Отчёты доступны руководителям проектов и администраторам"
        )
    if project_id is not None:
        ensure_project_access(db, user, project_id)
    if status and status not in STATUSES or severity and severity not in SEVERITIES:
        raise HTTPException(422, "Неизвестное состояние или критичность")
    try:
        start, end = analysis_period(date_from, date_to)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    return analysis(
        filtered(db, user, project_id, status, severity, start, end), start, end
    )


@router.get("/api/reports/risks/export.{format}")
def export_risk_analysis(
    format: str,
    project_id: int | None = None,
    status: str | None = None,
    severity: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    data = risk_analysis(project_id, status, severity, date_from, date_to, db, user)
    sections = report_sections(data)
    scope = (
        ensure_project_access(db, user, project_id).name
        if project_id is not None
        else "Все доступные проекты"
    )
    period = "Весь период"
    if date_from and date_to:
        period = f"Выявлены с {date_from:%d.%m.%Y} по {date_to:%d.%m.%Y}"
    elif date_from:
        period = f"Выявлены с {date_from:%d.%m.%Y}"
    elif date_to:
        period = f"Выявлены по {date_to:%d.%m.%Y}"
    title = f"Риски и реагирование. {scope}. {period}"
    if status:
        title += f". {STATUSES[status]}"
    if severity:
        title += f". {SEVERITIES[severity]}"
    if format == "xlsx":
        content = make_report_xlsx(title, sections)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif format == "pdf":
        content = make_report_pdf(title, sections)
        media = "application/pdf"
    else:
        raise HTTPException(422, "Доступны форматы xlsx и pdf")
    return Response(
        content,
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="risk-analysis.{format}"'
        },
    )


def validate_responsible(db: Session, risk: Risk, user_id: int) -> None:
    target = db.get(User, user_id)
    if target is None or target.is_blocked:
        raise HTTPException(422, "Ответственный не найден или заблокирован")
    if risk.project_id and target.role != "admin":
        ensure_project_participant(db, risk.project_id, user_id)
        manager = db.scalar(
            select(Project.manager_id).where(Project.project_id == risk.project_id)
        )
        member = db.get(ProjectMember, (risk.project_id, user_id))
        if manager != user_id and member is None:
            raise HTTPException(422, "Ответственный должен участвовать в проекте")


@router.post("/api/risks", response_model=IdResult, status_code=201)
def create_risk(
    body: RiskCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    ensure_project_access(db, user, body.project_id, write=True)
    if db.get(RiskType, body.risk_type_id) is None:
        raise HTTPException(422, "Тип риска не найден")
    if body.task_id:
        task = get_task(db, body.task_id)
        if task is None or task.project_id != body.project_id:
            raise HTTPException(422, "Задача не относится к указанному проекту")
    if (
        body.subject_user_id
        and db.get(ProjectMember, (body.project_id, body.subject_user_id)) is None
    ):
        raise HTTPException(422, "Сотрудник должен участвовать в проекте")
    if body.subject_user_id:
        ensure_project_participant(db, body.project_id, body.subject_user_id)
    risk = Risk(
        **body.model_dump(exclude={"severity"}),
        measured_value=None,
        status="new",
        is_viewed=False,
        is_cause_resolved=False,
    )
    if body.responsible_id:
        validate_responsible(db, risk, body.responsible_id)
    db.add(risk)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Для этого типа и объекта уже есть открытый риск")
    add_event(db, risk, user.user_id, "created_manual", "Риск добавлен вручную")
    add_event(db, risk, user.user_id, "severity_set", {"severity": body.severity})
    if risk.responsible_id:
        add_event(
            db, risk, user.user_id, "assigned", {"responsible_id": risk.responsible_id}
        )
        transition(db, risk, "reviewing", user.user_id)
    db.commit()
    return {"risk_id": risk.risk_id}


@router.get("/api/risks/{risk_id}", response_model=RiskDetail)
def get_risk(
    risk_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    risk = load_risk(db, user, risk_id)
    names = {
        uid: name for uid, name in db.execute(select(User.user_id, User.full_name))
    }
    manage = can_manage(db, user, risk)
    return {
        "risk": serialize_risks(db, user, [risk])[0],
        "actions": risk.actions,
        "can_manage": manage,
        "allowed_transitions": list(TRANSITIONS[risk.status]) if manage else [],
        "events": [
            {
                "event_id": e.event_id,
                "initiator_id": e.initiator_id,
                "initiator_name": names.get(e.initiator_id or 0),
                "event_type": e.event_type,
                "event_at": e.event_at,
                "details": e.details,
            }
            for e in reversed(risk.events)
        ],
    }


@router.post("/api/risks/{risk_id}/assign", response_model=OkResult)
def assign(
    risk_id: int,
    body: AssignmentIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    risk = load_risk(db, user, risk_id, write=True)
    ensure_open(risk)
    validate_responsible(db, risk, body.responsible_id)
    risk.responsible_id = body.responsible_id
    add_event(
        db, risk, user.user_id, "assigned", {"responsible_id": body.responsible_id}
    )
    if risk.status == "new":
        transition(db, risk, "reviewing", user.user_id)
    db.commit()
    return {"ok": True}


@router.post("/api/risks/{risk_id}/status", response_model=OkResult)
def status(
    risk_id: int,
    body: StatusIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    risk = load_risk(db, user, risk_id, write=True)
    transition(db, risk, body.status, user.user_id, body.comment)
    db.commit()
    return {"ok": True}


@router.post("/api/risks/{risk_id}/comments", response_model=OkResult)
def comment(
    risk_id: int,
    body: CommentIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    risk = load_risk(db, user, risk_id, write=True)
    ensure_open(risk)
    if not body.text.strip():
        raise HTTPException(422, "Введите текст комментария")
    add_event(db, risk, user.user_id, "comment", body.text.strip())
    db.commit()
    return {"ok": True}


@router.post("/api/risks/{risk_id}/view", response_model=OkResult)
def viewed(
    risk_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    risk = load_risk(db, user, risk_id, write=True)
    if not risk.is_viewed:
        risk.is_viewed = True
        add_event(db, risk, user.user_id, "viewed", "Риск просмотрен")
        db.commit()
    return {"ok": True}


@router.post("/api/risks/{risk_id}/actions", response_model=ActionOut, status_code=201)
def add_action(
    risk_id: int,
    body: ActionIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RiskAction:
    risk = load_risk(db, user, risk_id, write=True)
    ensure_open(risk)
    if risk.status == "new":
        raise HTTPException(409, "Сначала назначьте ответственного")
    action = RiskAction(risk_id=risk_id, **body.model_dump())
    risk.actions.append(action)
    db.flush()
    add_event(
        db,
        risk,
        user.user_id,
        "action_added",
        {"action_id": action.action_id, "description": action.description},
    )
    if risk.status == "reviewing":
        transition(db, risk, "in_progress", user.user_id)
    db.commit()
    return action


@router.put("/api/risk-actions/{action_id}", response_model=ActionOut)
def update_action(
    action_id: int,
    body: ActionUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RiskAction:
    action = db.get(RiskAction, action_id)
    if action is None:
        raise HTTPException(404, "Мероприятие не найдено")
    risk = load_risk(db, user, action.risk_id, write=True)
    ensure_open(risk)
    data = body.model_dump(exclude_unset=True)
    if any(value is None for key, value in data.items() if key != "due_date"):
        raise HTTPException(422, "Описание и состояние обязательны")
    for key, val in data.items():
        setattr(action, key, val)
    add_event(
        db,
        risk,
        user.user_id,
        "action_changed",
        {"action_id": action_id, **body.model_dump(exclude_unset=True, mode="json")},
    )
    db.commit()
    return action
