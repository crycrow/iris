from sqlalchemy import select
from sqlalchemy.orm import Session
from app.modules.risk_management.models import Risk, RiskType
from .lifecycle import OPEN_STATUSES, add_event
from .severity import risk_severity, calculate_severity


def finding_key(item: dict) -> tuple:
    return (
        item["risk_type_id"],
        item["project_id"],
        item["task_id"],
        item["subject_user_id"],
    )


def apply_findings(
    db: Session,
    findings: list[dict],
    types: dict[int, RiskType],
    project_ids: list[int],
    user_ids: set[int],
    initiator_id: int | None,
) -> dict:
    open_risks = list(db.scalars(select(Risk).where(Risk.status.in_(OPEN_STATUSES))))
    scoped = [
        r
        for r in open_risks
        if r.risk_type_id in types
        and (
            r.project_id in project_ids
            or r.project_id is None
            and r.subject_user_id in user_ids
        )
    ]
    indexed = {
        (r.risk_type_id, r.project_id, r.task_id, r.subject_user_id): r for r in scoped
    }
    seen = set()
    stats = {"created": 0, "updated": 0, "resolved": 0, "total_open": 0}
    for item in findings:
        key = finding_key(item)
        seen.add(key)
        risk = indexed.get(key)
        if risk is None:
            data = {k: v for k, v in item.items() if k != "suppressed_task_ids"}
            risk = Risk(**data, status="new", is_viewed=False, is_cause_resolved=False)
            db.add(risk)
            db.flush()
            add_event(
                db,
                risk,
                initiator_id,
                "created",
                "Риск выявлен по недельным показателям",
            )
            indexed[key] = risk
            stats["created"] += 1
        else:
            if risk.measured_value is None:

                continue
            old = risk_severity(risk)
            risk.measured_value = item["measured_value"]
            risk.description = item["description"]
            if risk.is_cause_resolved:
                add_event(
                    db,
                    risk,
                    initiator_id,
                    "cause_returned",
                    "Основание риска выявлено повторно",
                )
            risk.is_cause_resolved = False
            new = calculate_severity(types[risk.risk_type_id], item["measured_value"])
            if old != new:
                add_event(
                    db, risk, initiator_id, "severity_changed", {"from": old, "to": new}
                )
            stats["updated"] += 1
    for risk in scoped:
        key = (risk.risk_type_id, risk.project_id, risk.task_id, risk.subject_user_id)
        if (
            key not in seen
            and risk.measured_value is not None
            and not risk.is_cause_resolved
        ):
            risk.is_cause_resolved = True
            add_event(
                db,
                risk,
                initiator_id,
                "cause_resolved",
                "Условие риска больше не подтверждается. Статус сохранён",
            )
            stats["resolved"] += 1
    db.flush()
    stats["total_open"] = len(indexed)
    return stats
