from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.common.models import User, Project, ProjectMember
from app.common.schemas import ProjectIn, MembersIn
from app.common.permissions import (
    get_current_user,
    require_roles,
    ensure_project_access,
    accessible_project_ids,
    ensure_project_participant,
)
from app.common.services.access_log import audit
from app.common.services.people import name_sort_key
from app.common.services.project_summary import project_summary

router = APIRouter(prefix="/api/projects", tags=["Проекты"])
_calendar_provider = None


def register_calendar_provider(provider) -> None:
    global _calendar_provider
    _calendar_provider = provider


def serialize(db: Session, project: Project) -> dict:
    data = {c.name: getattr(project, c.name) for c in Project.__table__.columns}
    members = db.scalars(
        select(User)
        .join(ProjectMember, ProjectMember.user_id == User.user_id)
        .where(ProjectMember.project_id == project.project_id)
    ).all()
    data["members"] = [
        {
            "user_id": m.user_id,
            "full_name": m.full_name,
            "role": m.role,
            "project_role": (
                "manager" if m.user_id == project.manager_id else "employee"
            ),
            "job_title": m.job_title,
        }
        for m in sorted(members, key=lambda row: name_sort_key(row.full_name, row.user_id))
    ]
    manager = db.get(User, project.manager_id)
    data["manager_name"] = manager.full_name if manager else ""
    return data


def save_members(db: Session, project: Project, ids: list[int]) -> None:
    ids = list(set(ids + [project.manager_id]))
    old = set(
        db.scalars(
            select(ProjectMember.user_id).where(
                ProjectMember.project_id == project.project_id
            )
        )
    )
    found = list(
        db.scalars(
            select(User.user_id).where(
                User.user_id.in_(ids),
                User.is_blocked.is_(False) | User.user_id.in_(old),
            )
        )
    )
    if set(found) != set(ids):
        raise HTTPException(422, "Участник не найден или заблокирован")
    for uid in ids:
        participant = db.get(User, uid)
        if participant is None:
            raise HTTPException(422, "Участник не найден")
        if participant.role != "employee" and uid != project.manager_id:
            raise HTTPException(
                422,
                "В команду можно добавить только сотрудников и руководителя этого проекта",
            )
        if uid not in old:
            ensure_project_participant(db, project.project_id, uid)
    removed = old - set(ids)
    if removed:

        from app.core.integration import can_remove_members

        if not can_remove_members(db, project.project_id, removed):
            raise HTTPException(409, "Сначала снимите назначения удаляемых участников")
        db.execute(
            delete(ProjectMember).where(
                ProjectMember.project_id == project.project_id,
                ProjectMember.user_id.in_(removed),
            )
        )
    for uid in set(ids) - old:
        db.add(ProjectMember(project_id=project.project_id, user_id=uid))


def project_for_update(db: Session, user: User, project_id: int) -> Project:
    db.scalar(
        select(Project)
        .where(Project.project_id == project_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return ensure_project_access(db, user, project_id, write=True)


def validate_manager(db: Session, manager_id: int) -> None:
    manager = db.scalar(
        select(User)
        .where(User.user_id == manager_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not manager or manager.role not in ("admin", "manager") or manager.is_blocked:
        raise HTTPException(422, "Выберите действующего руководителя")


@router.get("")
def projects(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = list(
        db.scalars(
            select(Project)
            .where(Project.project_id.in_(accessible_project_ids(db, user)))
            .order_by(Project.project_id)
        )
    )
    return [serialize(db, row) for row in rows]


@router.get("/{project_id}")
def project(
    project_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = serialize(db, ensure_project_access(db, user, project_id))
    audit(
        user.user_id,
        "read",
        "project_members",
        [m["user_id"] for m in result["members"]],
    )
    return result


@router.post("", status_code=201)
def create(
    body: ProjectIn,
    user: User = Depends(require_roles("admin", "manager")),
    db: Session = Depends(get_db),
):
    manager_id = body.manager_id if body.manager_id is not None else user.user_id
    if user.role != "admin" and manager_id != user.user_id:
        raise HTTPException(403, "Можно создавать только свои проекты")
    validate_manager(db, manager_id)
    row = Project(
        **body.model_dump(exclude={"member_ids", "manager_id"}), manager_id=manager_id
    )
    db.add(row)
    db.flush()
    save_members(db, row, body.member_ids)
    if _calendar_provider:
        _calendar_provider(db, row)
    db.commit()
    return serialize(db, row)


@router.put("/{project_id}")
def update(
    project_id: int,
    body: ProjectIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = project_for_update(db, user, project_id)
    previous_manager_id = row.manager_id
    manager_id = body.manager_id if body.manager_id is not None else row.manager_id
    if user.role != "admin" and manager_id != previous_manager_id:
        raise HTTPException(403, "Смена руководителя доступна администратору")
    validate_manager(db, manager_id)
    previous_member_ids = list(
        db.scalars(
            select(ProjectMember.user_id).where(ProjectMember.project_id == project_id)
        )
    )
    member_ids = (
        list(body.member_ids)
        if "member_ids" in body.model_fields_set
        else previous_member_ids
    )
    if manager_id != previous_manager_id:
        from app.core.integration import can_remove_members

        if not can_remove_members(db, project_id, {previous_manager_id}):
            raise HTTPException(
                409, "Перед сменой руководителя снимите или переназначьте его задачи"
            )
        member_ids = [uid for uid in member_ids if uid != previous_manager_id]
    for key, value in body.model_dump(exclude={"member_ids", "manager_id"}).items():
        setattr(row, key, value)
    row.manager_id = manager_id
    save_members(db, row, member_ids)
    if _calendar_provider:
        _calendar_provider(db, row)
    db.commit()
    return serialize(db, row)


@router.put("/{project_id}/members")
def members(
    project_id: int,
    body: MembersIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = project_for_update(db, user, project_id)
    if row.manager_id not in body.user_ids:
        raise HTTPException(
            409,
            "Нельзя исключить руководителя проекта. Сначала назначьте нового руководителя",
        )
    save_members(db, row, body.user_ids)
    db.commit()
    audit(user.user_id, "update", "project_members", body.user_ids)
    return serialize(db, row)


@router.get("/{project_id}/summary")
def summary(
    project_id: int,
    user: User = Depends(require_roles("admin", "manager")),
    db: Session = Depends(get_db),
):
    row = ensure_project_access(db, user, project_id, write=True)
    return {"project": serialize(db, row), **project_summary(db, project_id)}


@router.get("/{project_id}/summary.{format}")
def export_summary(
    project_id: int,
    format: str,
    user: User = Depends(require_roles("admin", "manager")),
    db: Session = Depends(get_db),
):
    from fastapi import Response
    from app.common.exports.xlsx_base import make_report_xlsx
    from app.common.exports.pdf_base import make_report_pdf

    project = ensure_project_access(db, user, project_id, write=True)
    data = project_summary(db, project_id)
    sections = data.get("summary_sections", [])
    if not sections:
        sections = [
            {
                "title": "Состояние проекта",
                "headers": ["Показатель", "Значение"],
                "rows": [
                    ["Начало", project.start_date],
                    ["Завершение", project.end_date],
                ],
            }
        ]
    if format == "xlsx":
        content = make_report_xlsx(project.name, sections)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif format == "pdf":
        content = make_report_pdf(project.name, sections)
        media = "application/pdf"
    else:
        raise HTTPException(422, "Доступны форматы xlsx и pdf")
    return Response(
        content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="summary.{format}"'},
    )
