from collections import defaultdict
from datetime import datetime, timedelta
from app.modules.risk_management.models import RiskType
from ..catalog import parameters
from .base import compare, consecutive, finding, mature, value


def evaluate(rt: RiskType, context: dict) -> list[dict]:
    params = parameters(rt)
    if rt.rule_code == "systematic_estimation":
        candidates: dict[int, list[tuple[int, dict]]] = defaultdict(list)
        for key, rows in context["histories"].items():
            pid, tid, uid = key
            task = context["tasks"].get(tid)
            if (
                not task
                or uid
                or task.is_milestone
                or task.status in ("cancelled", "backlog", "todo")
                or not rows
                or rows[0]["week_start"] != context["week"]
            ):
                continue
            if task.status == "done":
                completed = context["completions"].get(tid)
                if isinstance(completed, str):
                    completed = datetime.fromisoformat(completed)
                if isinstance(completed, datetime):
                    completed = completed.date()
                if not completed or completed < context["as_of"] - timedelta(
                    days=int(params["history_days"])
                ):
                    continue
            if value(rows[0], "cpi") is not None:
                candidates[pid].append((tid, rows[0]))
        out = []
        for pid, items in candidates.items():
            deviating = [
                tid
                for tid, row in items
                if (cpi := value(row, "cpi")) is not None
                and cpi < params["cpi_threshold"]
                and abs(float(row["ev"] or 0) - float(row["ac"] or 0))
                >= params["h_min"]
            ]
            share = len(deviating) / len(items) * 100
            if len(deviating) >= params["N_min"] and compare(
                share, rt.condition_op, float(rt.threshold)
            ):
                item = finding(
                    rt,
                    (pid, None, None),
                    share,
                    f"Перерасход у {len(deviating)} из {len(items)} задач ({share:.1f} %). Задачи {', '.join(context['tasks'][tid].name for tid in deviating)}",
                )
                item["suppressed_task_ids"] = deviating
                out.append(item)
        return out
    out = []
    for key, rows in context["histories"].items():
        pid, tid, uid = key
        if not pid or uid or (rt.rule_code == "project_overrun") != (tid is None):
            continue
        task = context["tasks"].get(tid)
        if task and (
            task.is_milestone or task.status in ("cancelled", "backlog", "todo")
        ):
            continue

        def condition(row: dict) -> bool:
            return (
                compare(value(row, rt.metric), rt.condition_op, float(rt.threshold))
                and abs(float(row["ev"] or 0) - float(row["ac"] or 0))
                >= params["h_min"]
                and (rt.rule_code != "project_overrun" or mature(row, params["p_min"]))
            )

        if consecutive(rows, int(params["k"]), context["week"], condition):
            row = rows[0]
            measured = value(row, rt.metric)
            assert measured is not None
            out.append(
                finding(
                    rt,
                    key,
                    measured,
                    f"На выполненную работу затрачено на {float(row['ac']) - float(row['ev']):.1f} ч больше её плановой оценки",
                )
            )
    return out
