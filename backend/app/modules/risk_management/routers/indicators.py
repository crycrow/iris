from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Any
from sqlalchemy import select, or_, and_
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.common.models import User, ProjectMember
from app.common.permissions import get_current_user, ensure_project_access
from app.modules.risk_management.models import Risk
from app.modules.risk_management.schemas import RiskOut
from app.modules.risk_management.services.lifecycle import OPEN_STATUSES
from app.modules.risk_management.services.queries import serialize_risks, visibility

router = APIRouter(tags=["Индикаторы рисков"])


class Indicators(BaseModel):
    tasks: dict[str, list[RiskOut]]
    users: dict[str, list[RiskOut]]
    project: list[RiskOut]


@router.get("/api/projects/{project_id}/risk-indicators", response_model=Indicators)
def indicators(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    ensure_project_access(db, user, project_id)
    members = select(ProjectMember.user_id).where(
        ProjectMember.project_id == project_id
    )
    query = select(Risk).where(
        visibility(user),
        Risk.status.in_(OPEN_STATUSES),
        or_(
            Risk.project_id == project_id,
            and_(Risk.project_id.is_(None), Risk.subject_user_id.in_(members)),
        ),
    )
    result: dict[str, Any] = {"tasks": {}, "users": {}, "project": []}
    for item in serialize_risks(db, user, list(db.scalars(query))):
        if item["task_id"]:
            result["tasks"].setdefault(str(item["task_id"]), []).append(item)
        elif item["subject_user_id"]:
            result["users"].setdefault(str(item["subject_user_id"]), []).append(item)
        else:
            result["project"].append(item)
    return result
