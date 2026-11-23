from app.modules.risk_management.models import RiskType
from ..catalog import parameters
from .base import compare, consecutive, finding, value


def evaluate(rt: RiskType, context: dict) -> list[dict]:
    out = []
    params = parameters(rt)
    for key, rows in context["histories"].items():
        pid, tid, uid = key
        if (
            pid
            or tid
            or not uid
            or not rows
            or rows[0]["week_start"] != context["week"]
        ):
            continue
        row = rows[0]
        if rt.rule_code == "underload":
            measured = value(row, rt.metric)
            triggered = uid in context["active_users"] and compare(
                measured, rt.condition_op, float(rt.threshold)
            )
        else:
            planned = max(value(row, "u_plan") or 0, value(row, "u_plan_next") or 0)
            factual = consecutive(
                rows,
                int(params["fact_weeks"]),
                context["week"],
                lambda r: compare(
                    value(r, "u_fact"), rt.condition_op, float(rt.threshold)
                ),
            )
            if rt.metric == "u_fact":
                measured = value(row, "u_fact")
                triggered = factual
            else:
                measured = (
                    max(planned, value(row, "u_fact") or 0) if factual else planned
                )
                triggered = (
                    compare(planned, rt.condition_op, float(rt.threshold)) or factual
                )
        if triggered and measured is not None:
            out.append(
                finding(rt, key, measured, f"Загрузка {measured:.1f} % от нормы")
            )
    return out
