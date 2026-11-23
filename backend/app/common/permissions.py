from datetime import datetime, timezone
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session
import jwt
from app.core.config import settings
from app.core.database import get_db
from app.core.security import token_hash
from app.common.models import User, Project, ProjectMember, Session as LoginSession

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(401, "Требуется вход в систему")
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.secret_key,
            algorithms=["HS256"],
            options={"require": ["sub", "exp", "iat", "jti"]},
        )
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, ValueError, KeyError):
        raise HTTPException(401, "Сессия недействительна или истекла")
    session = db.scalar(
        select(LoginSession).where(
            LoginSession.token_hash == token_hash(credentials.credentials),
            LoginSession.user_id == user_id,
        )
    )
    now = datetime.now(timezone.utc)
    if session is None or session.expires_at.replace(tzinfo=timezone.utc) <= now:
        raise HTTPException(401, "Сессия завершена")
    user = db.get(User, user_id)
    if user is None or user.is_blocked:
        raise HTTPException(403, "Учётная запись заблокирована")
    request.state.user_id = user.user_id
    return user


def require_roles(*roles: str):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                403,
                (
                    "Доступно руководителям проектов и администраторам"
                    if "manager" in roles
                    else "Доступно только администратору"
                ),
            )
        return user

    return dependency


def accessible_project_ids(db: Session, user: User) -> list[int]:
    query = select(Project.project_id)
    if user.role == "manager":
        query = query.where(Project.manager_id == user.user_id)
    elif user.role == "employee":
        query = query.where(
            Project.project_id.in_(
                select(ProjectMember.project_id).where(
                    ProjectMember.user_id == user.user_id
                )
            )
        )
    return list(db.scalars(query))


def ensure_project_access(
    db: Session, user: User, project_id: int, write: bool = False
) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "Проект не найден")
    if user.role == "admin" or (
        user.role == "manager" and project.manager_id == user.user_id
    ):
        return project
    if (
        user.role == "employee"
        and not write
        and db.get(ProjectMember, (project_id, user.user_id)) is not None
    ):
        return project
    raise HTTPException(403, "Нет доступа к проекту")


def ensure_project_participant(db: Session, project_id: int, user_id: int) -> User:
    participant = db.scalar(
        select(User)
        .where(User.user_id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if participant is None or participant.is_blocked:
        raise HTTPException(422, "Сотрудник не найден или заблокирован")
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "Проект не найден")
    if participant.role != "employee" and participant.user_id != project.manager_id:
        raise HTTPException(
            422,
            "В команду можно добавить только сотрудников и руководителя этого проекта",
        )
    return participant
