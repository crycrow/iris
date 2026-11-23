from app.core.clock import today as app_today
from datetime import date
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.common.models import User
from app.common.permissions import get_current_user, ensure_project_access
from app.modules.time_tracking.models import MetricSnapshot
from app.modules.time_tracking.services.snapshots import compute_project_metrics

router = APIRouter(tags=["Показатели освоенного объёма"])


@router.get("/api/projects/{project_id}/metrics")
def metrics(
    project_id: int,
    as_of: date | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    ensure_project_access(db, user, project_id)
    data = compute_project_metrics(db, as_of or app_today(), [project_id])
    db.commit()
    return {
        "project": data["projects"][project_id],
        "tasks": list(data["tasks"].values()),
        "members": list(data["members"].values()),
    }


@router.get("/api/projects/{project_id}/snapshots")
def snapshots(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    ensure_project_access(db, user, project_id)
    return {
        "items": [
            {c.name: getattr(row, c.name) for c in MetricSnapshot.__table__.columns}
            for row in db.scalars(
                select(MetricSnapshot)
                .where(
                    MetricSnapshot.project_id == project_id,
                    MetricSnapshot.task_id.is_(None),
                    MetricSnapshot.user_id.is_(None),
                )
                .order_by(MetricSnapshot.week_start)
            )
        ]
    }
