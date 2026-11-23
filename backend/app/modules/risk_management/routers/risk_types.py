import math
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.common.models import User
from app.common.permissions import get_current_user
from app.modules.risk_management.models import RiskType, RiskTypeParam, Risk
from app.modules.risk_management.schemas import (
    RiskTypeCreate,
    RiskTypeUpdate,
    RiskTypeOut,
    CatalogOut,
)
from app.modules.risk_management.services.catalog import parameters
from app.modules.risk_management.services.severity import risk_severity
from app.modules.risk_management.services.lifecycle import add_event
from app.modules.risk_management.services.rules import custom

router = APIRouter(tags=["Справочник рисков"])


def serialize(item: RiskType) -> dict:
    return {
        **{c.name: getattr(item, c.name) for c in RiskType.__table__.columns},
        "params": parameters(item),
    }


@router.get("/api/risk-types", response_model=CatalogOut)
def list_types(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    return {
        "items": [
            serialize(r)
            for r in db.scalars(select(RiskType).order_by(RiskType.risk_type_id))
        ],
        "can_manage": user.role == "admin",
        "custom_options": {
            "objects": {"task": "Задача", "project": "Проект", "employee": "Сотрудник"},
            "metrics": {
                scope: [
                    {
                        "key": key,
                        "name": custom.METRICS[key][0],
                        "unit": custom.METRICS[key][1],
                    }
                    for key in custom.METRICS
                    if key in keys
                ]
                for scope, keys in custom.ALLOWED.items()
            },
        },
    }


@router.put("/api/risk-types/{type_id}", response_model=RiskTypeOut)
def update_type(
    type_id: int,
    body: RiskTypeUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    if user.role != "admin":
        raise HTTPException(403, "Справочник изменяет только администратор")
    item = db.get(RiskType, type_id)
    if item is None:
        raise HTTPException(404, "Тип риска не найден")
    affected = list(db.scalars(select(Risk).where(Risk.risk_type_id == type_id)))
    previous_severity = {risk.risk_id: risk_severity(risk) for risk in affected}
    data = body.model_dump(exclude_unset=True)
    if item.object_kind:
        custom.validate({**serialize(item), **data})
        values = data.pop("params", None)
        if values is not None:
            for param in item.params:
                param.param_value = values[param.param_name]
    else:
        if data.pop("object_kind", None) is not None:
            raise HTTPException(422, "Объект встроенного правила нельзя изменить")
        metric = data.get("metric", item.metric)
        allowed = {
            "task_overdue": {"delta_t"},
            "task_delay": {"spi"},
            "project_overdue": {"s"},
            "task_idle": {"t_safe"},
            "task_overrun": {"cpi"},
            "project_overrun": {"cpi"},
            "systematic_estimation": {"deviation_share"},
            "overload": {"u_plan", "u_fact"},
            "underload": {"u_plan"},
            "imbalance": {"imbalance"},
            "need_participant": {"capacity_gap"},
            "single_dependency": {"k"},
        }
        if metric not in allowed[item.rule_code]:
            raise HTTPException(
                422, "Показатель не соответствует объекту и правилу этого типа"
            )
        threshold = data.get("threshold", float(item.threshold))
        if (
            threshold is None
            or not math.isfinite(threshold)
            or threshold < 0
            or (metric in ("spi", "cpi") and not 0 < threshold < 1)
        ):
            raise HTTPException(
                422,
                "Укажите корректный порог, для относительных показателей сроков и трудозатрат строго между нулём и единицей",
            )
        values = data.pop("params", None)
        if values is not None:
            required = parameters(item)
            if set(values) != set(required) or any(
                not math.isfinite(v) or v < 0 for v in values.values()
            ):
                raise HTTPException(
                    422, "Передайте полный набор неотрицательных параметров этого типа"
                )
            for key in ("k", "fact_weeks", "N_min", "history_days", "team_min"):
                if key in values and (values[key] < 1 or not values[key].is_integer()):
                    raise HTTPException(
                        422,
                        "Число недель, задач и участников должно быть положительным целым",
                    )
            for key in ("p_min",):
                if key in values and not 0 <= values[key] <= 100:
                    raise HTTPException(
                        422, "Процент должен находиться между нулём и ста"
                    )
            if "cpi_threshold" in values and not 0 < values["cpi_threshold"] < 1:
                raise HTTPException(
                    422,
                    "Порог эффективности трудозатрат должен быть строго между нулём и единицей",
                )
            if "days_high" in values and (
                values["days_high"] < threshold or values["days_critical"] < 1
            ):
                raise HTTPException(
                    422, "Границы критичности должны быть не ниже порога срабатывания"
                )
            if "load_high" in values and values["load_high"] < threshold:
                raise HTTPException(
                    422,
                    "Граница высокой критичности должна быть не ниже порога перегрузки",
                )
            for lo, hi in (
                ("days_high", "days_critical"),
                ("load_high", "load_critical"),
            ):
                if lo in values and values[lo] >= values[hi]:
                    raise HTTPException(
                        422, "Граница высокой критичности должна быть ниже критической"
                    )
            for param in item.params:
                param.param_value = values[param.param_name]
    for key, val in data.items():
        if val is None:
            raise HTTPException(422, "Поля справочника нельзя обнулить")
        setattr(item, key, val)
    for risk in affected:
        level = risk_severity(risk)
        if level != previous_severity[risk.risk_id]:
            add_event(
                db,
                risk,
                user.user_id,
                "severity_changed",
                {
                    "from": previous_severity[risk.risk_id],
                    "to": level,
                    "reason": "Изменены настройки типа риска",
                },
            )
    db.commit()
    return serialize(item)


@router.post("/api/risk-types", response_model=RiskTypeOut, status_code=201)
def create_type(
    body: RiskTypeCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    if user.role != "admin":
        raise HTTPException(403, "Справочник изменяет только администратор")
    data = body.model_dump()
    custom.validate(data)
    params = data.pop("params")
    data["name"] = data["name"].strip()
    data["risk_group"] = data["risk_group"].strip()
    item = RiskType(code=f"custom_{uuid4().hex[:20]}", **data)
    item.params = [
        RiskTypeParam(param_name=key, param_value=val) for key, val in params.items()
    ]
    db.add(item)
    db.commit()
    return serialize(item)
