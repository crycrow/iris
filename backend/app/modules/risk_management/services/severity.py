import json
from app.modules.risk_management.models import Risk, RiskType
from .catalog import parameters


def calculate_severity(
    risk_type: RiskType, value: float | None, manual_severity: str | None = None
) -> str:

    if value is None:
        return manual_severity or risk_type.severity
    if risk_type.object_kind:
        return risk_type.severity
    params = parameters(risk_type)
    if risk_type.metric in {"spi", "cpi"}:
        theta = 1 - float(risk_type.threshold)
        delta = 1 - value
        if theta <= 0:
            return risk_type.severity
        ratio = round(delta / theta, 8)
        return "critical" if ratio >= 3 else "high" if ratio >= 2 else "medium"
    if risk_type.metric in {"delta_t", "s"}:
        return (
            "critical"
            if value >= params["days_critical"]
            else "high" if value >= params["days_high"] else "medium"
        )
    if risk_type.rule_code == "overload":
        return (
            "critical"
            if value > params["load_critical"]
            else "high" if value >= params["load_high"] else "medium"
        )
    return risk_type.severity


def risk_severity(risk: Risk) -> str:
    manual = None
    if risk.measured_value is None:
        for event in reversed(risk.events):
            if event.event_type == "severity_set":
                manual = json.loads(event.details).get("severity")
                break
    return calculate_severity(
        risk.risk_type,
        None if risk.measured_value is None else float(risk.measured_value),
        manual,
    )
