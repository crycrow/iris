from sqlalchemy import select
from sqlalchemy.orm import Session
from app.modules.risk_management.models import RiskType, RiskTypeParam

CATALOG: list[tuple[str, str, str, str, str, float, str, str, dict[str, float]]] = [
    (
        "task_overdue",
        "Нарушение срока задачи",
        "Сроки",
        "delta_t",
        "gte",
        1,
        "medium",
        "Пересмотреть срок задачи и доступные ресурсы",
        {"days_high": 4, "days_critical": 8},
    ),
    (
        "task_delay",
        "Отставание задачи от плана",
        "Сроки",
        "spi",
        "lt",
        0.85,
        "medium",
        "Уточнить прогресс и устранить причины отставания",
        {"h_min": 8, "k": 2},
    ),
    (
        "project_overdue",
        "Нарушение срока проекта",
        "Сроки",
        "s",
        "gte",
        1,
        "medium",
        "Пересмотреть календарный план и согласовать срок проекта",
        {"p_min": 20, "k": 2, "days_high": 4, "days_critical": 8},
    ),
    (
        "task_idle",
        "Задача без списаний времени",
        "Сроки",
        "t_safe",
        "gt",
        10,
        "medium",
        "Уточнить состояние задачи и внести фактические часы",
        {},
    ),
    (
        "task_overrun",
        "Перерасход трудозатрат по задаче",
        "Точность оценки",
        "cpi",
        "lt",
        0.85,
        "medium",
        "Разобрать причины перерасхода и уточнить оценку",
        {"h_min": 8, "k": 2},
    ),
    (
        "project_overrun",
        "Перерасход трудозатрат по проекту",
        "Точность оценки",
        "cpi",
        "lt",
        0.90,
        "medium",
        "Проверить затраты задач и прогноз итоговых трудозатрат",
        {"h_min": 8, "k": 2, "p_min": 20},
    ),
    (
        "systematic_estimation",
        "Систематическая ошибка оценок",
        "Точность оценки",
        "deviation_share",
        "gte",
        30,
        "high",
        "Пересмотреть методику оценки на основе завершённых задач",
        {"N_min": 3, "cpi_threshold": 0.85, "h_min": 8, "history_days": 90},
    ),
    (
        "overload",
        "Перегрузка сотрудника",
        "Перегрузка и простой",
        "u_plan",
        "gt",
        100,
        "medium",
        "Перераспределить задачи с учётом всех проектов сотрудника",
        {"fact_weeks": 3, "load_high": 110, "load_critical": 120},
    ),
    (
        "underload",
        "Недостаточная загрузка",
        "Перегрузка и простой",
        "u_plan",
        "lt",
        50,
        "medium",
        "Назначить работу с учётом компетенций сотрудника",
        {},
    ),
    (
        "imbalance",
        "Неэффективное распределение работ",
        "Доступность ресурсов",
        "imbalance",
        "gte",
        1,
        "medium",
        "Перенести часть задач от перегруженных участников к недогруженным",
        {},
    ),
    (
        "need_participant",
        "Потребность в дополнительном участнике",
        "Доступность ресурсов",
        "capacity_gap",
        "gt",
        0,
        "high",
        "Запросить дополнительного участника или сократить объём работ",
        {},
    ),
    (
        "single_dependency",
        "Зависимость от одного участника",
        "Доступность ресурсов",
        "k",
        "gte",
        75,
        "medium",
        "Распределить знания и оставшиеся задачи между участниками",
        {"team_min": 2},
    ),
]


def seed_risk_types(db: Session) -> None:
    for (
        code,
        name,
        group,
        metric,
        op,
        threshold,
        severity,
        recommendation,
        params,
    ) in CATALOG:
        if db.scalar(select(RiskType).where(RiskType.code == code)):
            continue
        item = RiskType(
            code=code,
            name=name,
            description=name,
            risk_group=group,
            metric=metric,
            condition_op=op,
            threshold=threshold,
            severity=severity,
            recommendation=recommendation,
            is_active=True,
        )
        item.params = [
            RiskTypeParam(param_name=key, param_value=value)
            for key, value in params.items()
        ]
        db.add(item)
    db.flush()


def parameters(risk_type: RiskType) -> dict[str, float]:
    return {row.param_name: float(row.param_value) for row in risk_type.params}
