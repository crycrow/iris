from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.clock import today
from app.core.database import get_db
from app.common.models import User
from app.common.permissions import require_roles, ensure_project_access
from app.common.services.access_log import audit
from app.modules.time_tracking.schemas.analytics import ProjectAnalytics
from app.modules.time_tracking.services.analytics import load_project_analytics

router = APIRouter(tags=["Графики отчётов"])


@router.get("/api/projects/{project_id}/analytics", response_model=ProjectAnalytics)
def project_analytics(
    project_id: int,
    date_from: date | None = None,
    date_to: date | None = None,
    user_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "manager")),
) -> ProjectAnalytics:
    project = ensure_project_access(db, user, project_id, write=True)
    try:
        result = load_project_analytics(db, project, today(), date_from, date_to, user_id)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    audit(
        user.user_id,
        "read",
        "project_analytics.users",
        [person.user_id for person in result.employees],
    )
    return result
