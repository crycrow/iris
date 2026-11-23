from fastapi import HTTPException
from sqlalchemy import select, or_, and_, false, true
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.orm import Session
from app.common.models import User, Project, ProjectMember
from app.common.services.access_log import audit
from app.modules.risk_management.models import Risk
from .lifecycle import STATUS_NAMES
from .severity import risk_severity
from .readers import task_names


def visibility(user: User) -> ColumnElement[bool]:
    if user.role == "admin":
        return true()
    membership = select(ProjectMember.project_id).where(
        ProjectMember.user_id == user.user_id
    )
    projects = (
        select(Project.project_id).where(Project.manager_id == user.user_id)
        if user.role == "manager"
        else membership
    )
    return or_(
        Risk.project_id.in_(projects),
        and_(Risk.project_id.is_(None), Risk.subject_user_id == user.user_id),
        (
            and_(
                Risk.project_id.is_(None),
                Risk.subject_user_id.in_(
                    select(ProjectMember.user_id)
                    .join(User, User.user_id == ProjectMember.user_id)
                    .join(Project, Project.project_id == ProjectMember.project_id)
                    .where(
                        ProjectMember.project_id.in_(projects),
                        or_(
                            User.role == "employee",
                            ProjectMember.user_id == Project.manager_id,
                        ),
                    )
                ),
            )
            if user.role == "manager"
            else false()
        ),
    )


def can_manage(db: Session, user: User, risk: Risk) -> bool:
    if user.role == "admin":
        return True
    if user.role != "manager":
        return False
    if risk.project_id:
        return (
            db.scalar(
                select(Project.manager_id).where(Project.project_id == risk.project_id)
            )
            == user.user_id
        )
    return bool(
        db.scalar(
            select(ProjectMember.user_id)
            .join(Project, Project.project_id == ProjectMember.project_id)
            .join(User, User.user_id == ProjectMember.user_id)
            .where(
                Project.manager_id == user.user_id,
                ProjectMember.user_id == risk.subject_user_id,
                or_(
                    User.role == "employee", ProjectMember.user_id == Project.manager_id
                ),
            )
        )
    )


def load_risk(db: Session, user: User, risk_id: int, write: bool = False) -> Risk:
    risk = db.scalar(select(Risk).where(Risk.risk_id == risk_id, visibility(user)))
    if risk is None:
        raise HTTPException(404, "Риск не найден или недоступен")
    if write and not can_manage(db, user, risk):
        raise HTTPException(403, "Доступно руководителям проектов и администраторам")
    return risk


def serialize_risks(db: Session, user: User, risks: list[Risk]) -> list[dict]:
    projects = {
        pid: name for pid, name in db.execute(select(Project.project_id, Project.name))
    }
    users = {
        uid: name for uid, name in db.execute(select(User.user_id, User.full_name))
    }
    tasks = task_names(db, [r.task_id for r in risks if r.task_id is not None])
    result = []
    for risk in risks:
        item = {col.name: getattr(risk, col.name) for col in Risk.__table__.columns}
        item.update(
            type_name=risk.risk_type.name,
            type_code=risk.risk_type.code,
            risk_group=risk.risk_type.risk_group,
            project_name=projects.get(risk.project_id or 0),
            task_name=tasks.get(risk.task_id or 0),
            subject_name=users.get(risk.subject_user_id or 0),
            responsible_name=users.get(risk.responsible_id or 0),
            recommendation=risk.risk_type.recommendation,
            threshold=float(risk.risk_type.threshold),
            metric=risk.risk_type.metric,
            severity=risk_severity(risk),
            status_name=STATUS_NAMES[risk.status],
            can_manage=can_manage(db, user, risk),
        )
        result.append(item)
    audit(
        user.user_id,
        "read",
        "risk_user_data",
        sorted(
            {
                uid
                for risk in risks
                for uid in (risk.subject_user_id, risk.responsible_id)
                if uid is not None
            }
        ),
    )
    return result
