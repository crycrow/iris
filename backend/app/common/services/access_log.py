import json
import logging
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

logger = logging.getLogger("access")


def configure_access_log() -> None:
    if logger.handlers:
        return
    folder = Path(os.environ.get("LOG_DIR", "logs"))
    folder.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        folder / "access.jsonl", maxBytes=5_000_000, backupCount=10, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def audit(
    user_id: int, action: str, resource: str, identifiers: list[int] | None = None
) -> None:
    configure_access_log()
    logger.info(
        json.dumps(
            {
                "at": datetime.now(timezone.utc).isoformat(),
                "user_id": user_id,
                "action": action,
                "resource": resource,
                "ids": identifiers or [],
            },
            ensure_ascii=False,
        )
    )
