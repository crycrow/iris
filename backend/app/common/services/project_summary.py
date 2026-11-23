from collections.abc import Callable
from typing import Any

_providers: dict[str, Callable[..., Any]] = {}


def register_provider(name: str, provider: Callable[..., Any]) -> None:
    _providers[name] = provider


def project_summary(db, project_id: int) -> dict:
    data = {
        name: provider(db, project_id)
        for name, provider in _providers.items()
        if name != "summary_sections"
    }
    if "summary_sections" in _providers:
        data["summary_sections"] = _providers["summary_sections"](db, project_id, data)
    return data
