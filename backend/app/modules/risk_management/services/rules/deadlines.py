from app.modules.risk_management.models import RiskType
from ..catalog import parameters
from .base import compare, consecutive, finding, mature, value


def evaluate(rt: RiskType, context: dict) -> list[dict]:
    out = []
    params = parameters(rt)
    for key, rows in context["histories"].items():
        project_id, task_id, user_id = key
        if (
            user_id
            or not project_id
            or not rows
            or rows[0]["week_start"] != context["week"]
        ):
            continue
        if (rt.rule_code == "project_overdue") != (task_id is None):
            continue
        task = context["tasks"].get(task_id)
        if task and task.status in ("done", "cancelled"):
            continue
        row = rows[0]
        measured = value(row, rt.metric)
        if measured is None or not compare(
            measured, rt.condition_op, float(rt.threshold)
        ):
            continue
        if rt.rule_code == "task_idle" and (
            not task or task.status not in ("dev", "review", "testing")
        ):
            continue
        if rt.rule_code == "task_delay":
            if task and task.is_milestone:
                continue

            def condition(item: dict) -> bool:
                return (
                    compare(
                        value(item, rt.metric), rt.condition_op, float(rt.threshold)
                    )
                    and abs(float(item["ev"] or 0) - float(item["pv"] or 0))
                    >= params["h_min"]
                )

            if not consecutive(rows, int(params["k"]), context["week"], condition):
                continue
        if rt.rule_code == "project_overdue" and float(row["delta_t"] or 0) < 1:

            def condition(item: dict) -> bool:
                return mature(item, params["p_min"]) and compare(
                    value(item, rt.metric), rt.condition_op, float(rt.threshold)
                )

            if not consecutive(rows, int(params["k"]), context["week"], condition):
                continue
        explanations = {
            "delta_t": f"Плановый срок нарушен на {measured:g} рабочих дней",
            "spi": f"Выполнено {measured * 100:.1f} % от объёма, запланированного к дате анализа",
            "s": f"Ожидаемое завершение позже плана на {measured:g} рабочих дней",
            "t_safe": f"По задаче не списывали время {measured:g} рабочих дней",
        }
        out.append(
            finding(rt, key, measured, explanations.get(rt.metric, rt.description))
        )
    return out
