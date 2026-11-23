from app.modules.risk_management.models import RiskType
from ..catalog import parameters
from .base import compare, finding, value


def evaluate(
    rt: RiskType, context: dict, user_findings: dict[str, set[int]]
) -> list[dict]:
    out = []
    params = parameters(rt)
    if rt.rule_code == "imbalance":
        for pid, members in context["members"].items():
            overloaded = members & user_findings.get("overload", set())
            underloaded = members & user_findings.get("underload", set())
            if (
                overloaded
                and underloaded
                and compare(1, rt.condition_op, float(rt.threshold))
            ):
                out.append(
                    finding(
                        rt,
                        (pid, None, None),
                        1,
                        f"Перегружены {len(overloaded)}, недогружены {len(underloaded)} участников",
                    )
                )
        return out
    for key, rows in context["histories"].items():
        pid, tid, uid = key
        if not pid or tid or not rows or rows[0]["week_start"] != context["week"]:
            continue
        if rt.rule_code == "single_dependency":
            if not uid or len(context["members"].get(pid, ())) < params["team_min"]:
                continue
        elif uid:
            continue
        measured = value(rows[0], rt.metric)
        if measured is not None and compare(
            measured, rt.condition_op, float(rt.threshold)
        ):
            explanation = (
                f"Доля остатка работ {measured:.1f} %"
                if uid
                else f"Остаток работ {float(rows[0]['w']):.2f} ч превышает мощность {float(rows[0]['m']):.2f} ч на {measured:.2f} ч"
            )
            out.append(finding(rt, key, measured, explanation))
    return out
