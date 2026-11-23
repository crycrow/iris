from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import hash_password
from app.common.models import User, Project, ProjectMember, Session as LoginSession
from app.common.schemas import UserOut, UserCreate, UserUpdate
from app.common.permissions import require_roles
from app.common.services.access_log import audit
from app.common.services.people import name_sort_key

router = APIRouter(prefix="/api/users", tags=["Пользователи"])


@router.get("", response_model=list[UserOut])
def users(
    q: str = "",
    user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    query = select(User).order_by(User.full_name)
    if q:
        query = query.where(User.full_name.ilike(f"%{q}%") | User.login.ilike(f"%{q}%"))
    result = list(db.scalars(query))
    result.sort(key=lambda row: name_sort_key(row.full_name, row.user_id))
    audit(user.user_id, "read", "users", [u.user_id for u in result])
    return result


@router.get("/options")
def options(
    user: User = Depends(require_roles("admin", "manager")),
    db: Session = Depends(get_db),
):
    result = list(
        db.scalars(
            select(User).where(User.is_blocked.is_(False)).order_by(User.full_name)
        )
    )
    result.sort(key=lambda row: name_sort_key(row.full_name, row.user_id))
    audit(user.user_id, "read", "user_names", [u.user_id for u in result])
    return [
        {
            "user_id": u.user_id,
            "full_name": u.full_name,
            "role": u.role,
            "job_title": u.job_title,
        }
        for u in result
    ]


@router.post("", response_model=UserOut, status_code=201)
def create(
    body: UserCreate,
    user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    if db.scalar(select(User).where(User.login == body.login.strip())):
        raise HTTPException(409, "Логин уже занят")
    data = body.model_dump(exclude={"password"})
    data["full_name"] = " ".join(data["full_name"].split())
    data["login"] = data["login"].strip()
    target = User(**data, password_hash=hash_password(body.password))
    db.add(target)
    db.commit()
    db.refresh(target)
    audit(user.user_id, "create", "users", [target.user_id])
    return target


@router.put("/{user_id}", response_model=UserOut)
def update(
    user_id: int,
    body: UserUpdate,
    user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    target = db.scalar(
        select(User)
        .where(User.user_id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if target is None:
        raise HTTPException(404, "Пользователь не найден")
    if user_id == user.user_id and (
        body.is_blocked or body.role not in (None, "admin")
    ):
        raise HTTPException(
            409, "Нельзя заблокировать себя или снять свою роль администратора"
        )
    if (body.is_blocked or body.role == "employee") and db.scalar(
        select(Project.project_id).where(Project.manager_id == user_id).limit(1)
    ) is not None:
        raise HTTPException(
            409, "Сначала передайте проекты пользователя другому руководителю"
        )
    if body.role in ("manager", "admin") and body.role != target.role:
        from app.modules.time_tracking.models import Task, TaskAssignment

        foreign_membership = db.scalar(
            select(ProjectMember.user_id)
            .join(Project)
            .where(ProjectMember.user_id == user_id, Project.manager_id != user_id)
            .limit(1)
        )
        foreign_assignment = db.scalar(
            select(TaskAssignment.assignment_id)
            .join(Task)
            .join(Project)
            .where(TaskAssignment.user_id == user_id, Project.manager_id != user_id)
            .limit(1)
        )
        if foreign_membership is not None or foreign_assignment is not None:
            raise HTTPException(
                409,
                "Сначала исключите сотрудника из команд других проектов и снимите его назначения",
            )
    for key, value in body.model_dump(exclude_unset=True, exclude={"password"}).items():
        if value is not None:
            if key == "full_name":
                value = " ".join(value.split())
            setattr(target, key, value)
    if body.password:
        target.password_hash = hash_password(body.password)
    if body.password or body.is_blocked or body.role:
        db.execute(delete(LoginSession).where(LoginSession.user_id == target.user_id))
    db.commit()
    audit(user.user_id, "update", "users", [target.user_id])
    return target
