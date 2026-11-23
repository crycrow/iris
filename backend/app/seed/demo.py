import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.models import Project, ProjectMember, SystemSetting, User
from app.core.clock import today as local_today
from app.core.security import hash_password
from app.modules.risk_management.models import Risk, RiskAction
from app.modules.risk_management.services.catalog import seed_risk_types
from app.modules.risk_management.services.engine import run_risk_scan
from app.modules.risk_management.services.lifecycle import add_event
from app.modules.time_tracking.models import (
    Release,
    ResourcePlan,
    Task,
    TaskActivity,
    TaskAssignment,
    TimeEntry,
)
from app.modules.time_tracking.services.snapshots import compute_and_store_snapshot
from app.modules.time_tracking.services.working_calendar import (
    ensure_calendar,
    read_calendar,
)
from .portfolio import ADMIN_NAME, MANAGER_NAMES, JOB_TITLES, PROJECTS, dated_range, employee_name, task_blueprint
from .profile_upgrade import upgrade_demo_profiles
from .project_names import upgrade_project_names
from .enrichment import enrich_demo, latest_work_day

DATASET_VERSION = "priisk-2026-2"


def create_users(db: Session) -> dict[str, User]:
    users = {user.login: user for user in db.scalars(select(User))}
    definitions = [
        (
            "admin",
            "admin123",
            ADMIN_NAME,
            "admin",
            "Администратор информационных систем",
        )
    ]
    definitions.extend(
        (f"manager{i}", "manager123", name, "manager", "Руководитель проекта")
        for i, name in enumerate(MANAGER_NAMES, 1)
    )
    definitions.extend(
        (
            f"employee{i}",
            "employee123",
            employee_name(i),
            "employee",
            JOB_TITLES[(i - 1) % 7] if i <= 77 else "Ведущий консультант по внедрению",
        )
        for i in range(1, 84)
    )
    hashes = {password: hash_password(password) for _, password, _, _, _ in definitions}
    for login, password, name, role, title in definitions:
        if login in users:
            if users[login].job_title == "Специалист":
                users[login].job_title = title
            continue
        user = User(
            login=login,
            password_hash=hashes[password],
            full_name=name,
            role=role,
            job_title=title,
            email=f"{login}@demo.example",
            is_blocked=False,
        )
        db.add(user)
        db.flush()
        users[login] = user
    return users


def create_settings(db: Session) -> None:
    values = {
        "daily_hours": "8",
        "weekly_hours": "40",
        "token_minutes": "480",
        "p_min": "20",
        "k": "2",
        "scheduler_day": "sun",
        "scheduler_hour": "23",
        "scheduler_minute": "55",
        "calendar_holidays": json.dumps(
            [f"2026-01-{d:02d}" for d in range(1, 10)]
            + [
                "2026-02-23",
                "2026-03-08",
                "2026-03-09",
                "2026-05-01",
                "2026-05-09",
                "2026-05-11",
                "2026-06-12",
                "2026-11-04",
                "2026-12-31",
            ]
        ),
        "calendar_shortened": json.dumps(
            ["2026-04-30", "2026-05-08", "2026-06-11", "2026-11-03"]
        ),
        "calendar_overrides": "{}",
    }
    existing = set(db.scalars(select(SystemSetting.setting_key)))
    for key, value in values.items():
        if key not in existing:
            db.add(
                SystemSetting(
                    setting_key=key, setting_value=value, description="Параметр системы"
                )
            )
    db.flush()


def progress_on(task: Task, finish: date, as_of: date) -> tuple[int, str]:
    if as_of < task.start_date:
        return 0, "todo" if (task.start_date - as_of).days <= 14 else "backlog"
    if as_of >= finish:
        return 100, "done"
    elapsed = (as_of - task.start_date).days + 1
    duration = max((finish - task.start_date).days + 1, 1)
    progress = min(95, max(5, round(elapsed / duration * 100 / 5) * 5))
    status = (
        "review"
        if progress >= 85
        else (
            "testing"
            if "проверк" in task.name.lower() or "испытан" in task.name.lower()
            else "dev"
        )
    )
    return progress, status


def build_portfolio(
    db: Session,
    users: dict[str, User],
    existing_projects: dict[int, Project] | None = None,
) -> None:
    today = local_today()
    monday = today - timedelta(days=today.weekday())
    generated: list[tuple[Task, TaskAssignment, date]] = []
    groups: dict[int, list[Task]] = defaultdict(list)
    milestones: list[Task] = []
    project_ids: list[int] = []
    for index, (name, description, service, subjects, age) in enumerate(PROJECTS):
        manager = users[f"manager{(0, 1, 0, 1, 2, 2, 3, 3, 4, 4, 5)[index] + 1}"]
        start = monday - timedelta(weeks=age)
        end = start + timedelta(weeks=21, days=-3)
        project = (existing_projects or {}).get(index)
        if project is None:
            project = Project(
                name=name,
                description=description,
                manager_id=manager.user_id,
                start_date=start,
                end_date=end,
                planned_hours=0,
                status="active",
            )
            db.add(project)
            db.flush()
        else:
            project.name = name
            project.description = description
            project.start_date = min(start, project.start_date)
            project.end_date = max(end, project.end_date)
            project.manager_id = manager.user_id
        project_ids.append(project.project_id)
        team = [users[f"employee{index * 7 + j + 1}"] for j in range(7)] + [manager]
        consultant = users[f"employee{78 + index % 6}"]
        for member in team + [consultant]:
            if db.get(ProjectMember, (project.project_id, member.user_id)) is None:
                db.add(
                    ProjectMember(project_id=project.project_id, user_id=member.user_id)
                )
        db.flush()
        ensure_calendar(db, project)
        releases = []
        for release_name, week in (
            ("Первая рабочая поставка", 13),
            ("Пилотная эксплуатация", 18),
            ("Промышленная эксплуатация", 21),
        ):
            release = Release(
                project_id=project.project_id,
                name=release_name,
                release_date=start + timedelta(weeks=week, days=-3),
                description=f"{release_name} платформы ПРИИСК для {service}",
            )
            db.add(release)
            db.flush()
            releases.append(release)
        for phase_index, (phase, week_start, week_end, tasks) in enumerate(
            task_blueprint(service, subjects)
        ):
            phase_start, phase_end = dated_range(start, week_start, week_end)
            parent = Task(
                project_id=project.project_id,
                name=phase,
                start_date=phase_start,
                due_date=phase_end,
                status="todo",
                progress_pct=0,
            )
            db.add(parent)
            db.flush()
            for task_index, (title, role, begin, end_week) in enumerate(tasks):
                task_start, task_end = dated_range(start, begin, end_week)
                finish = task_end
                if index in (0, 4, 7) and phase_index == 2 and task_index in (5, 8):
                    finish += timedelta(days=10 if index == 0 else 5)
                release = releases[
                    0 if phase_index <= 2 else 1 if phase_index == 3 else 2
                ]
                task = Task(
                    project_id=project.project_id,
                    parent_task_id=parent.task_id,
                    release_id=release.release_id,
                    name=title,
                    description=f"Подготовить результат и согласовать его с командой {service}. Результат включается в поставку «{release.name}».",
                    start_date=task_start,
                    due_date=task_end,
                    progress_pct=0,
                    status="todo",
                )
                task.progress_pct, task.status = progress_on(task, finish, today)
                db.add(task)
                db.flush()
                assignment = TaskAssignment(
                    task_id=task.task_id, user_id=team[role].user_id
                )
                db.add(assignment)
                db.flush()
                generated.append((task, assignment, finish))
                groups[parent.task_id].append(task)
                if phase_index in (1, 3) and task_index == 0:
                    secondary = TaskAssignment(
                        task_id=task.task_id, user_id=consultant.user_id
                    )
                    db.add(secondary)
                    db.flush()
                    generated.append((task, secondary, finish))
            milestone = Task(
                project_id=project.project_id,
                release_id=releases[
                    0 if phase_index <= 2 else 1 if phase_index == 3 else 2
                ].release_id,
                name=f"Согласован этап «{phase.lower()}»",
                is_milestone=True,
                start_date=phase_end,
                due_date=phase_end,
                progress_pct=100 if today >= phase_end else 0,
                status="done" if today >= phase_end else "todo",
            )
            db.add(milestone)
            milestones.append(milestone)
        for period in range(7):
            task_start, task_end = dated_range(start, period * 3, (period + 1) * 3)
            task = Task(
                project_id=project.project_id,
                name=f"Координация поставки и работа с заказчиком, этап {period + 1}",
                description="Планирование работ, разбор рисков, согласование результатов и контроль договорённостей.",
                start_date=task_start,
                due_date=task_end,
                progress_pct=0,
                status="todo",
            )
            task.progress_pct, task.status = progress_on(task, task_end, today)
            db.add(task)
            db.flush()
            assignment = TaskAssignment(task_id=task.task_id, user_id=manager.user_id)
            db.add(assignment)
            db.flush()
            generated.append((task, assignment, task_end))
    db.flush()
    allocate_hours(db, generated, latest_work_day(db, today) - timedelta(days=1))
    for task, assignment, finish in generated:
        if task.start_date <= today:
            db.add(
                TaskActivity(
                    task_id=task.task_id,
                    user_id=assignment.user_id,
                    change_type="comment",
                    new_value=(
                        "Результат размещён в рабочем пространстве проекта"
                        if task.status == "done"
                        else "Работа выполняется по согласованному плану"
                    ),
                    changed_at=datetime.combine(
                        min(today, finish), datetime.min.time(), timezone.utc
                    ),
                )
            )
    for project_id in project_ids:
        project = db.get(Project, project_id)
        assert project is not None
        project.planned_hours = db.scalar(
            select(func.coalesce(func.sum(ResourcePlan.planned_hours), 0))
            .join(TaskAssignment)
            .join(Task)
            .where(Task.project_id == project_id)
        )
    db.flush()
    for offset in (35, 28, 21, 14, 7, 0):
        as_of = monday - timedelta(days=offset) + timedelta(days=6) if offset else today
        for task, _, finish in generated:
            task.progress_pct, task.status = progress_on(task, finish, as_of)
        for parent_id, children in groups.items():
            stored_parent = db.get(Task, parent_id)
            assert stored_parent is not None
            stored_parent.progress_pct = round(
                sum(task.progress_pct for task in children) / len(children)
            )
            stored_parent.status = (
                "done"
                if stored_parent.progress_pct == 100
                else "todo" if stored_parent.progress_pct == 0 else "dev"
            )
        for milestone in milestones:
            milestone.progress_pct = 100 if as_of >= milestone.due_date else 0
            milestone.status = "done" if milestone.progress_pct else "todo"
        db.flush()
        compute_and_store_snapshot(db, as_of, project_ids)
    previous_risk_ids = set(db.scalars(select(Risk.risk_id)))
    run_risk_scan(db, today, None, project_ids)
    db.flush()
    for index, risk in enumerate(
        db.scalars(
            select(Risk)
            .where(
                Risk.project_id.in_(project_ids),
                Risk.status == "new",
                Risk.is_viewed.is_(False),
            )
            .order_by(Risk.risk_id)
        )
    ):
        if risk.risk_id in previous_risk_ids or index % 4 == 0:
            continue
        risk_project = db.get(Project, risk.project_id)
        assert risk_project is not None
        risk.responsible_id = risk_project.manager_id
        risk.status = "in_progress" if index % 3 else "reviewing"
        risk.is_viewed = True
        db.add(
            RiskAction(
                risk_id=risk.risk_id,
                description=(
                    "Уточнить оставшиеся работы с исполнителем и согласовать план завершения"
                    if risk.task_id
                    else "Проверить загрузку команды и перераспределить ближайшие работы"
                ),
                due_date=today + timedelta(days=5 + index % 5),
                execution_state=(
                    "in_progress" if risk.status == "in_progress" else "planned"
                ),
            )
        )
        add_event(
            db,
            risk,
            risk.responsible_id,
            "status",
            {
                "from": "new",
                "to": "reviewing",
                "comment": "Риск разобран на проектной встрече",
            },
        )
        if risk.status == "in_progress":
            add_event(
                db,
                risk,
                risk.responsible_id,
                "status",
                {
                    "from": "reviewing",
                    "to": "in_progress",
                    "comment": "Согласовано мероприятие",
                },
            )
    marker = db.scalar(
        select(SystemSetting).where(SystemSetting.setting_key == "demo_dataset_version")
    )
    if marker is None:
        db.add(
            SystemSetting(
                setting_key="demo_dataset_version",
                setting_value=DATASET_VERSION,
                description="Версия демонстрационного набора",
            )
        )
    else:
        marker.setting_value = DATASET_VERSION
    db.flush()


def allocate_hours(
    db: Session, generated: list[tuple[Task, TaskAssignment, date]], today: date
) -> None:
    by_user: dict[int, list[tuple[Task, TaskAssignment, date]]] = defaultdict(list)
    for item in generated:
        by_user[item[1].user_id].append(item)
    calendars = {
        project_id: read_calendar(db, project_id)
        for project_id in {task.project_id for task, _, _ in generated}
    }
    existing_actual = defaultdict(float)
    for user_id, day, hours in db.execute(
        select(
            TimeEntry.user_id, TimeEntry.work_date, func.sum(TimeEntry.hours)
        ).group_by(TimeEntry.user_id, TimeEntry.work_date)
    ):
        existing_actual[user_id, day] = float(hours)
    plans: dict[tuple[int, date], float] = defaultdict(float)
    for user_id, assignments in by_user.items():
        day = min(task.start_date for task, _, _ in assignments)
        end = max(finish for _, _, finish in assignments)
        while day <= end:
            eligible_plan = [
                (task, assignment)
                for task, assignment, _ in assignments
                if task.start_date <= day <= task.due_date
                and calendars[task.project_id].get(day, 0) > 0
            ]
            eligible_fact = [
                (task, assignment)
                for task, assignment, finish in assignments
                if task.start_date <= day <= finish
                and calendars[task.project_id].get(day, 0) > 0
            ]
            for eligible, actual in ((eligible_plan, False), (eligible_fact, True)):
                if not eligible or actual and day > today:
                    continue
                capacity = min(calendars[task.project_id][day] for task, _ in eligible)
                if actual:
                    if (day.toordinal() + user_id * 11) % 23 == 0:
                        capacity -= 1
                    capacity = max(0, capacity - existing_actual[user_id, day])
                units = int(capacity * 2)
                portions = [
                    units // len(eligible) + (index < units % len(eligible))
                    for index in range(len(eligible))
                ]
                for (task, assignment), portion in zip(eligible, portions):
                    hours = portion / 2
                    if not hours:
                        continue
                    if actual:
                        db.add(
                            TimeEntry(
                                user_id=user_id,
                                task_id=task.task_id,
                                work_date=day,
                                hours=hours,
                                comment=(
                                    "Согласование решений и контроль выполнения"
                                    if "Координация" in task.name
                                    else "Работа по задаче, результат сохранён в проекте"
                                ),
                            )
                        )
                    else:
                        plans[assignment.assignment_id, day.replace(day=1)] += hours
            day += timedelta(days=1)
    for (assignment_id, month), hours in plans.items():
        db.add(
            ResourcePlan(
                assignment_id=assignment_id, plan_month=month, planned_hours=hours
            )
        )
    db.flush()


def seed_all(db: Session) -> None:
    if db.scalar(select(User.user_id).limit(1)) is not None:
        upgrade_demo_profiles(db, local_today())
        upgrade_project_names(db)
        return
    create_settings(db)
    users = create_users(db)
    seed_risk_types(db)
    build_portfolio(db, users)
    enrich_demo(db, local_today())
    upgrade_demo_profiles(db, local_today())
    upgrade_project_names(db)
