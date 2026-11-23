

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.models import Project, SystemSetting, User
from .portfolio import (
    LEGACY_PROJECT_NAMES, ORIGINAL_PROJECT_NAMES, PREVIOUS_PROJECT_NAMES, PROJECTS,
)
from .profile_upgrade import (
    INTERNAL_PROJECT_NAME, PREVIOUS_INTERNAL_PROJECT_NAME,
    VERSION_ONE_CUSTOMER_NAMES, VERSION_TWO_CUSTOMER_NAMES,
)

MARKER_KEY = "demo_project_names_version"
REVISION = "generic-project-names-1"


def upgrade_project_names(db: Session) -> dict:
    marker = db.scalar(select(SystemSetting).where(SystemSetting.setting_key == MARKER_KEY))
    if marker is not None and marker.setting_value == REVISION:
        return {"already_applied": True}
    dataset = db.scalar(select(SystemSetting.setting_value).where(
        SystemSetting.setting_key == "demo_dataset_version"
    ))
    admin_id = db.scalar(select(User.user_id).where(User.login == "admin"))
    if not dataset or not dataset.startswith("priisk-") or admin_id is None:
        return {"skipped_non_demo": True}

    renamed = 0
    for index, definition in enumerate(PROJECTS):


        project = db.get(Project, index + 1)
        aliases = {names[index] for names in (
            LEGACY_PROJECT_NAMES, ORIGINAL_PROJECT_NAMES, PREVIOUS_PROJECT_NAMES,
        )}
        if index > 0:
            aliases.update(f"Внедрение ПРИИСК. {names[index - 1]}" for names in (
                VERSION_ONE_CUSTOMER_NAMES, VERSION_TWO_CUSTOMER_NAMES,
            ))
        if project is not None and project.name in aliases and project.name != definition[0]:
            project.name = definition[0]
            renamed += 1


    for project in db.scalars(select(Project).where(
        Project.name == PREVIOUS_INTERNAL_PROJECT_NAME,
        Project.manager_id == admin_id,
    )):
        project.name = INTERNAL_PROJECT_NAME
        renamed += 1

    stats = {"projects_renamed": renamed}
    if marker is None:
        marker = SystemSetting(setting_key=MARKER_KEY, setting_value=REVISION)
        db.add(marker)
    else:
        marker.setting_value = REVISION
    marker.description = json.dumps(stats, ensure_ascii=False)
    db.flush()
    return stats
