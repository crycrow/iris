from datetime import date
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.common.models import Project, User
from app.modules.risk_management.models import RiskType
from .readers import load_context
from .dedup import apply_findings
from .rules import deadlines, estimation, load, availability, custom


def run_risk_scan(
    db: Session,
    as_of: date,
    initiator_id: int | None,
    project_ids: list[int] | None = None,
) -> dict:

    query = select(Project.project_id).where(Project.status.in_(("planned", "active")))
    if project_ids is not None:
        query = query.where(Project.project_id.in_(project_ids))
    if initiator_id is not None:
        user = db.get(User, initiator_id)
        if user is None or user.role not in ("admin", "manager"):
            from fastapi import HTTPException

            raise HTTPException(
                403, "Анализ доступен руководителям проектов и администраторам"
            )
        if user.role == "manager":
            query = query.where(Project.manager_id == user.user_id)
    ids = list(db.scalars(query))
    if not ids:
        return {"created": 0, "updated": 0, "resolved": 0, "total_open": 0}
    context = load_context(db, as_of, ids)
    types = list(db.scalars(select(RiskType).where(RiskType.is_active.is_(True))))
    findings = []
    users: dict[str, set[int]] = {}
    for rt in types:
        if rt.object_kind:
            findings.extend(custom.evaluate(rt, context))
        elif rt.rule_code in (
            "task_overdue",
            "task_delay",
            "project_overdue",
            "task_idle",
        ):
            findings.extend(deadlines.evaluate(rt, context))
        elif rt.rule_code in (
            "task_overrun",
            "project_overrun",
            "systematic_estimation",
        ):
            findings.extend(estimation.evaluate(rt, context))
        elif rt.rule_code in ("overload", "underload"):
            found = load.evaluate(rt, context)
            findings.extend(found)
            users.setdefault(rt.rule_code, set()).update(
                f["subject_user_id"] for f in found
            )
    for rt in types:
        if rt.rule_code in ("imbalance", "need_participant", "single_dependency"):
            findings.extend(availability.evaluate(rt, context, users))

    suppressed = {
        tid for item in findings for tid in item.get("suppressed_task_ids", [])
    }
    task_overrun_ids = {
        rt.risk_type_id for rt in types if rt.rule_code == "task_overrun"
    }
    findings = [
        f
        for f in findings
        if not (f["risk_type_id"] in task_overrun_ids and f["task_id"] in suppressed)
    ]
    all_users = (
        set().union(*context["members"].values()) if context["members"] else set()
    )
    return apply_findings(
        db,
        findings,
        {rt.risk_type_id: rt for rt in types},
        ids,
        all_users,
        initiator_id,
    )
