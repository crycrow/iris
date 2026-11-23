from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.common.models import User
from app.common.permissions import get_current_user, ensure_project_access
from app.modules.time_tracking.models import Task, Release
from app.modules.time_tracking.schemas import ReleaseCreate, Items, Result
from app.modules.time_tracking.services.task_view import task_rows

router = APIRouter(tags=["Релизы"])


@router.get("/api/projects/{project_id}/releases", response_model=Items)
def releases(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    ensure_project_access(db, user, project_id)
    tasks = task_rows(
        db, list(db.scalars(select(Task).where(Task.project_id == project_id)))
    )
    parent_ids = {t["parent_task_id"] for t in tasks}
    items = []
    for release in db.scalars(
        select(Release)
        .where(Release.project_id == project_id)
        .order_by(Release.release_date)
    ):
        children = [
            t
            for t in tasks
            if t["release_id"] == release.release_id
            and t["task_id"] not in parent_ids
            and t["status"] != "cancelled"
        ]
        bac = sum(t["planned_hours"] for t in children)
        progress = (
            sum(t["planned_hours"] * t["progress_pct"] for t in children) / bac
            if bac
            else 0
        )
        items.append(
            {
                **{c.name: getattr(release, c.name) for c in Release.__table__.columns},
                "progress": progress,
                "tasks_total": len(children),
                "tasks_done": sum(t["status"] == "done" for t in children),
            }
        )
    return {"items": items}


@router.post(
    "/api/projects/{project_id}/releases",
    response_model=dict[str, int],
    status_code=201,
)
def create_release(
    project_id: int,
    body: ReleaseCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    ensure_project_access(db, user, project_id, write=True)
    release = Release(project_id=project_id, **body.model_dump())
    db.add(release)
    db.commit()
    return {"release_id": release.release_id}


@router.put("/api/releases/{release_id}", response_model=Result)
def update_release(
    release_id: int,
    body: ReleaseCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    release = db.get(Release, release_id)
    if release is None:
        raise HTTPException(404, "Релиз не найден")
    ensure_project_access(db, user, release.project_id, write=True)
    for key, value in body.model_dump().items():
        setattr(release, key, value)
    db.commit()
    return {"ok": True}


@router.delete("/api/releases/{release_id}", response_model=Result)
def delete_release(
    release_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    release = db.get(Release, release_id)
    if release is None:
        raise HTTPException(404, "Релиз не найден")
    ensure_project_access(db, user, release.project_id, write=True)
    if db.scalar(select(Task.task_id).where(Task.release_id == release_id).limit(1)):
        raise HTTPException(409, "Сначала перенесите задачи из релиза")
    db.delete(release)
    db.commit()
    return {"ok": True}
