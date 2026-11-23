

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
import json

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.common.models import Project, ProjectMember, SystemSetting, User
from app.modules.risk_management.models import Risk, RiskAction
from app.modules.risk_management.services.lifecycle import (
    OPEN_STATUSES, add_event, transition,
)
from app.modules.time_tracking.models import (
    Task, TaskActivity, TimeEntry,
)
from app.modules.time_tracking.services.resource_plan import assign_task
from app.modules.time_tracking.services.working_calendar import ensure_calendar, read_calendar
from .portfolio import (
    ADMIN_NAME, MANAGER_NAMES, PROJECTS, ORIGINAL_PROJECT_NAMES,
    LEGACY_PROJECT_NAMES, employee_name,
)

PREVIOUS_REVISION = "priisk-profiles-2026-1"
VERSION_TWO = "priisk-profiles-2026-2"
REVISION = "priisk-profiles-2026-3"
MARKER_KEY = "demo_profile_upgrade_version"
INTERNAL_PROJECT_NAME = "Внутренние задачи"
PREVIOUS_INTERNAL_PROJECT_NAME = "Внутренние задачи Ирис"
VERSION_ONE_CUSTOMER_NAMES = (
    "Северный банк", "Ладога Трейд", "Орбита Сервис", "Промресурс Волга",
    "Линия Маркета", "Рубеж Страхование", "Северомаш Технологии",
    "Меридиан Транс", "Вертикаль Кадры", "Академия Перспектива",
)
VERSION_TWO_CUSTOMER_NAMES = (
    "Лиорент", "Кванторель", "Северолис", "Альмирекс", "Велорис",
    "Эстравель", "Меридиора", "Талвентис", "Ориалис", "Неворика",
)


def rename_version_one_projects(db: Session) -> int:
    renamed = 0


    for project_id, old_name in enumerate(VERSION_ONE_CUSTOMER_NAMES, 2):
        project = db.get(Project, project_id)
        prior_names = {f"Внедрение ПРИИСК. {name}" for name in
                       (old_name, VERSION_TWO_CUSTOMER_NAMES[project_id - 2])}
        if project is not None and project.name in prior_names:
            project.name = PROJECTS[project_id - 1][0]
            renamed += 1
    return renamed


def unique_demo_surnames(users: dict[str, User]) -> int:
    renamed = 0
    for login, full_name in demo_names().items():
        if login not in users:
            continue
        user = users[login]
        parts = user.full_name.split(maxsplit=1)
        if len(parts) != 2:
            continue

        replacement = full_name.split()[0] + " " + parts[1]
        if user.full_name != replacement:
            user.full_name = replacement
            renamed += 1
    return renamed


def demo_names() -> dict[str, str]:
    return {
        "admin": ADMIN_NAME,
        **{f"manager{i}": name for i, name in enumerate(MANAGER_NAMES, 1)},
        **{f"employee{i}": employee_name(i) for i in range(1, 84)},
    }


def create_internal_project(db: Session, users: dict[str, User], as_of: date) -> dict:
    admin = users["admin"]
    project = db.scalar(select(Project).where(
        Project.name.in_((INTERNAL_PROJECT_NAME, PREVIOUS_INTERNAL_PROJECT_NAME))
    ))
    if project is not None:

        return {"internal_project_id": project.project_id, "internal_created": 0}

    monday = as_of - timedelta(days=as_of.weekday())
    start, end = monday - timedelta(weeks=3), monday + timedelta(weeks=4, days=4)
    project = Project(
        name=INTERNAL_PROJECT_NAME, manager_id=admin.user_id,
        description="Поддержка рабочих мест, доступов и внутренних сервисов компании Ирис",
        start_date=start, end_date=end, status="active", planned_hours=0,
    )
    db.add(project)
    db.flush()
    team_logins = [login for login in ("admin", "employee1", "employee6", "employee13", "employee20") if login in users]
    for login in team_logins:
        db.add(ProjectMember(project_id=project.project_id, user_id=users[login].user_id))
    db.flush()
    ensure_calendar(db, project, as_of)
    calendar = read_calendar(db, project.project_id)

    definitions = [
        ("Администрирование учётных записей и прав доступа", 40,
         "Настроить доступы новых сотрудников и проверить актуальность прав", {"admin": 48, "employee6": 16}),
        ("Проверка резервных копий и восстановления базы", 60,
         "Проверить расписание копирования и восстановить копию в тестовой среде", {"admin": 24, "employee6": 16}),
        ("Обновление рабочих мест и служебного ПО", 50,
         "Установить согласованные обновления и проверить рабочие приложения", {"admin": 8, "employee13": 24}),
        ("Обработка внутренних обращений сотрудников", 40,
         "Разобрать обращения по доступам, рабочим местам и внутренним сервисам", {"admin": 48, "employee1": 16}),
        ("Актуализация базы знаний и инструкций поддержки", 25,
         "Обновить инструкции по типовым обращениям и входу в корпоративные сервисы", {"admin": 8, "employee1": 20}),
        ("Проверка доступности сервисов и журналов ошибок", 70,
         "Проверить состояние внутренних сервисов и разобрать повторяющиеся ошибки", {"admin": 32, "employee20": 16}),
    ]
    tasks_by_user: dict[int, list[Task]] = defaultdict(list)
    for name, progress, description, allocations in definitions:
        task = Task(
            project_id=project.project_id, name=name, description=description,
            start_date=start, due_date=end, status="dev", progress_pct=progress,
        )
        db.add(task)
        db.flush()
        db.add(TaskActivity(
            task_id=task.task_id, user_id=admin.user_id, change_type="comment",
            new_value="Согласованы состав работ и план внутренних задач поддержки",
        ))
        for login, hours in allocations.items():
            if login not in users:
                continue
            target = users[login]
            assign_task(db, task, target.user_id, Decimal(hours))
            project.planned_hours += Decimal(hours)
            tasks_by_user[target.user_id].append(task)



    work_days = [day for day in sorted(calendar) if start <= day <= as_of and calendar[day] > 0][-12:]
    daily = {
        (uid, day): Decimal(hours)
        for uid, day, hours in db.execute(
            select(TimeEntry.user_id, TimeEntry.work_date, func.sum(TimeEntry.hours))
            .where(TimeEntry.user_id.in_(tasks_by_user), TimeEntry.work_date >= start, TimeEntry.work_date <= as_of)
            .group_by(TimeEntry.user_id, TimeEntry.work_date)
        )
    }
    entries_created = 0
    for user_id, assigned in tasks_by_user.items():
        for index, day in enumerate(work_days):
            capacity = Decimal(str(calendar[day]))
            spare = max(Decimal(0), capacity - daily.get((user_id, day), Decimal(0)))
            requested = Decimal((4, 3, 5, 4)[index % 4]) if user_id == admin.user_id else Decimal("1")
            hours = min(spare, requested)
            hours = (hours * 2 // 1) / 2
            if hours < Decimal("0.5"):
                continue
            task = assigned[index % len(assigned)]
            db.add(TimeEntry(
                user_id=user_id, task_id=task.task_id, work_date=day, hours=hours,
                comment=task.description,
            ))
            daily[user_id, day] = daily.get((user_id, day), Decimal(0)) + hours
            entries_created += 1
    db.flush()
    return {"internal_project_id": project.project_id, "internal_created": 1,
            "tasks_created": len(definitions), "entries_created": entries_created}


def close_resolved_risks(db: Session, admin_id: int, as_of: date) -> dict:
    resolved = list(db.scalars(
        select(Risk).where(Risk.status.in_(OPEN_STATUSES), Risk.is_cause_resolved.is_(True))
        .order_by(Risk.detected_at, Risk.risk_id)
    ))

    keep = min(2, len(resolved) // 3)
    closing = resolved[:-keep] if keep else resolved
    for risk in closing:
        if risk.responsible_id is None:
            risk.responsible_id = admin_id
            add_event(db, risk, admin_id, "assigned", {"responsible_id": admin_id})
        risk.is_viewed = True
        if risk.status == "new":
            transition(db, risk, "reviewing", admin_id, "Основание риска устранено")
        if risk.status == "reviewing":
            verification = RiskAction(
                description="Подтвердить устранение основания риска по текущим показателям",
                due_date=as_of, execution_state="done",
            )
            risk.actions.append(verification)
            db.flush()
            add_event(db, risk, admin_id, "action_added", {
                "action_id": verification.action_id, "description": verification.description,
            })
            transition(db, risk, "in_progress", admin_id, "Проверка устранённого основания завершена")
        transition(db, risk, "closed", admin_id, "Основание устранено, риск закрыт после проверки")
    db.flush()
    return {"resolved_closed": len(closing), "resolved_left_open": keep}


def upgrade_demo_profiles(db: Session, as_of: date) -> dict:
    marker = db.scalar(select(SystemSetting).where(SystemSetting.setting_key == MARKER_KEY))
    if marker is not None and marker.setting_value == REVISION:
        return {"already_applied": True}
    dataset = db.scalar(select(SystemSetting.setting_value).where(SystemSetting.setting_key == "demo_dataset_version"))
    users = {user.login: user for user in db.scalars(select(User))}
    if not dataset or not dataset.startswith("priisk-") or "admin" not in users:
        return {"skipped_non_demo": True}

    if marker is not None and marker.setting_value in (PREVIOUS_REVISION, VERSION_TWO):


        stats = {"projects_renamed": rename_version_one_projects(db),
                 "surnames_renamed": unique_demo_surnames(users)}
        marker.setting_value = REVISION
        marker.description = json.dumps(stats, ensure_ascii=False)
        db.flush()
        return stats

    stats: dict = {"users_renamed": 0, "projects_renamed": 0}
    for login, name in demo_names().items():
        if login in users and users[login].full_name != name:
            users[login].full_name = name
            stats["users_renamed"] += 1
    aliases = {
        alias: PROJECTS[index][0]
        for names in (ORIGINAL_PROJECT_NAMES, LEGACY_PROJECT_NAMES)
        for index, alias in enumerate(names)
    }
    for project in db.scalars(select(Project)):
        if project.name in aliases and project.name != aliases[project.name]:
            project.name = aliases[project.name]
            stats["projects_renamed"] += 1
    stats["projects_renamed"] += rename_version_one_projects(db)
    stats.update(create_internal_project(db, users, as_of))
    stats.update(close_resolved_risks(db, users["admin"].user_id, as_of))
    if marker is None:
        marker = SystemSetting(setting_key=MARKER_KEY, setting_value=REVISION)
        db.add(marker)
    else:
        marker.setting_value = REVISION
    marker.description = json.dumps(stats, ensure_ascii=False)
    db.flush()
    return stats
