from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from app.common.models import Project, ProjectMember, SystemSetting, User
from app.core.database import Base
from app.modules.risk_management.models import Risk, RiskEvent, RiskType
from app.modules.time_tracking.models import Task, TaskAssignment, TimeEntry, ResourcePlan
from app.seed import demo
from app.seed.portfolio import (
    ORIGINAL_PROJECT_NAMES, LEGACY_PROJECT_NAMES, PREVIOUS_PROJECT_NAMES,
    PROJECTS, ADMIN_NAME,
)
from app.seed.profile_upgrade import (
    INTERNAL_PROJECT_NAME, PREVIOUS_INTERNAL_PROJECT_NAME, MARKER_KEY,
    PREVIOUS_REVISION, VERSION_TWO, REVISION,
    VERSION_ONE_CUSTOMER_NAMES, VERSION_TWO_CUSTOMER_NAMES, demo_names, upgrade_demo_profiles,
)
from app.seed.project_names import (
    MARKER_KEY as PROJECT_NAMES_MARKER_KEY,
    REVISION as PROJECT_NAMES_REVISION,
    upgrade_project_names,
)

AS_OF = date(2026, 11, 13)


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


def populate_old_demo(db):
    users = []
    for index, login in enumerate(demo_names(), 1):
        role = "admin" if login == "admin" else "manager" if login.startswith("manager") else "employee"
        users.append(User(user_id=index, login=login, full_name=f"Старое Имя {index}", role=role, password_hash="preserve"))
    db.add_all(users)
    db.add(User(user_id=200, login="custom", full_name="Пользователь Собственный", role="employee", password_hash="custom"))
    db.add(SystemSetting(setting_key="demo_dataset_version", setting_value="priisk-2026-2"))
    db.flush()
    for index, name in enumerate(ORIGINAL_PROJECT_NAMES, 1):
        db.add(Project(project_id=index, name=name, manager_id=2, start_date=date(2026, 1, 1), end_date=date(2026, 12, 31)))
    db.flush()
    risk_type = RiskType(code="profile-test", name="Test", risk_group="Test", metric="s", condition_op="gt", threshold=1, severity="high")
    db.add(risk_type)
    db.flush()
    for index in range(1, 9):
        task = Task(task_id=index, project_id=1, name=f"Existing task {index}", start_date=date(2026, 1, 1), due_date=date(2026, 12, 31))
        db.add(task)
        db.flush()
        db.add(Risk(risk_id=index, risk_type_id=risk_type.risk_type_id, task_id=index, project_id=1, responsible_id=2,
                    status="reviewing", is_cause_resolved=index <= 7))
    employee6 = next(u for u in users if u.login == "employee6")
    db.add(TimeEntry(entry_id=1, user_id=employee6.user_id, task_id=1, work_date=AS_OF, hours=Decimal("7.5"), comment="Existing work"))
    db.commit()
    return users


def test_upgrade_preserves_identity_and_history_and_is_idempotent(db):
    users = populate_old_demo(db)
    identity_before = [(u.user_id, u.login, u.password_hash) for u in users]

    stats = upgrade_demo_profiles(db, AS_OF)
    db.commit()

    assert stats["users_renamed"] == 90
    assert stats["projects_renamed"] == 11
    assert [(u.user_id, u.login, u.password_hash) for u in users] == identity_before
    assert {u.login: u.full_name for u in users} == demo_names()
    assert db.get(User, 200).full_name == "Пользователь Собственный"
    assert [db.get(Project, i).name for i in range(1, 12)] == [p[0] for p in PROJECTS]
    assert db.get(TimeEntry, 1).hours == Decimal("7.5")
    assert db.get(TimeEntry, 1).comment == "Existing work"
    assert stats["resolved_closed"] == 5
    assert stats["resolved_left_open"] == 2
    assert db.get(Risk, 8).status == "reviewing"
    closed = list(db.scalars(select(Risk).where(Risk.status == "closed")))
    assert all(risk.closed_at and risk.is_cause_resolved for risk in closed)
    assert all(any(event.event_type == "status" and '"to": "closed"' in event.details for event in risk.events) for risk in closed)

    counts = [db.scalar(select(func.count()).select_from(model)) for model in (Project, Task, TaskAssignment, ResourcePlan, TimeEntry, RiskEvent)]
    users[0].full_name = "Новое Пользовательское Имя"
    assert upgrade_demo_profiles(db, AS_OF) == {"already_applied": True}
    assert users[0].full_name == "Новое Пользовательское Имя"
    assert counts == [db.scalar(select(func.count()).select_from(model)) for model in (Project, Task, TaskAssignment, ResourcePlan, TimeEntry, RiskEvent)]


def test_internal_support_has_admin_work_and_valid_assignments(db):
    populate_old_demo(db)
    upgrade_demo_profiles(db, AS_OF)
    internal = db.scalar(select(Project).where(Project.name == INTERNAL_PROJECT_NAME))
    assert internal.manager_id == 1
    assert db.get(ProjectMember, (internal.project_id, 1)) is not None
    tasks = list(db.scalars(select(Task).where(Task.project_id == internal.project_id)))
    assert len(tasks) == 6
    entries = list(db.scalars(select(TimeEntry).where(TimeEntry.task_id.in_([t.task_id for t in tasks]))))
    assert any(entry.user_id == 1 for entry in entries)
    assert any(entry.user_id != 1 for entry in entries)
    assignments = {(a.task_id, a.user_id) for a in db.scalars(select(TaskAssignment))}
    assert all((entry.task_id, entry.user_id) in assignments for entry in entries)
    assert all(entry.work_date <= AS_OF and entry.hours >= Decimal("0.5") for entry in entries)
    totals = db.execute(select(TimeEntry.user_id, TimeEntry.work_date, func.sum(TimeEntry.hours)).group_by(TimeEntry.user_id, TimeEntry.work_date))
    assert all(hours <= 8 for _, _, hours in totals)


def test_existing_seed_runs_upgrade_without_rebuilding_projects(db, monkeypatch):
    populate_old_demo(db)
    monkeypatch.setattr(demo, "local_today", lambda: AS_OF)
    monkeypatch.setattr(demo, "build_portfolio", lambda *_args: pytest.fail("Existing portfolio must not be rebuilt"))
    demo.seed_all(db)
    assert db.scalar(select(SystemSetting).where(SystemSetting.setting_key == MARKER_KEY)) is not None
    assert db.get(Task, 1).name == "Existing task 1"


def test_new_seed_names_are_surname_first_and_distinct(db, monkeypatch):
    monkeypatch.setattr(demo, "hash_password", lambda password: "test-hash")
    users = demo.create_users(db)
    names = [u.full_name for u in users.values()]
    assert len(names) == len(set(names)) == 90
    assert all(len(name.split()) == 3 for name in names)
    assert users["admin"].full_name == ADMIN_NAME
    assert users["employee1"].full_name == "Иванов Алексей Сергеевич"
    assert users["manager1"].full_name == "Смирнова Анна Сергеевна"


def test_non_demo_database_is_not_modified(db):
    admin = User(login="admin", full_name="Custom Owner", role="admin", password_hash="keep")
    db.add(admin)
    db.flush()
    assert upgrade_demo_profiles(db, AS_OF) == {"skipped_non_demo": True}
    assert admin.full_name == "Custom Owner"
    assert db.scalar(select(func.count()).select_from(Project)) == 0


@pytest.mark.parametrize("prior_version, prior_names", [
    (PREVIOUS_REVISION, VERSION_ONE_CUSTOMER_NAMES),
    (VERSION_TWO, VERSION_TWO_CUSTOMER_NAMES),
])
def test_revision_three_only_renames_known_profiles_and_projects(db, prior_version, prior_names):
    populate_old_demo(db)
    upgrade_demo_profiles(db, AS_OF)
    marker = db.scalar(select(SystemSetting).where(SystemSetting.setting_key == MARKER_KEY))
    marker.setting_value = prior_version
    for project_id, name in enumerate(prior_names, 2):
        db.get(Project, project_id).name = f"Внедрение ПРИИСК. {name}"
    db.get(Project, 3).name = "Название, выбранное пользователем"
    db.get(User, 1).full_name = "Изменённое Пользователем Имя"
    db.get(User, 9).full_name = "Иванова Мария Андреевна"
    db.add(Project(project_id=99, manager_id=2, name="Внедрение ПРИИСК. Северный банк",
                   start_date=date(2026, 1, 1), end_date=date(2026, 12, 31)))
    db.commit()
    before = {
        model.__tablename__: [tuple(row) for row in db.execute(select(model.__table__))]
        for model in (Task, TaskAssignment, ResourcePlan, TimeEntry, Risk, RiskEvent)
    }
    identity_before = [(u.user_id, u.login, u.password_hash, u.full_name.split(maxsplit=1)[1])
                       for u in db.scalars(select(User).order_by(User.user_id))]
    assert upgrade_demo_profiles(db, AS_OF) == {"projects_renamed": 9, "surnames_renamed": 2}
    assert marker.setting_value == REVISION
    assert db.get(Project, 1).name == "Развитие платформы"
    assert db.get(Project, 2).name == "Обслуживание клиентов банка"
    assert db.get(Project, 3).name == "Название, выбранное пользователем"
    assert db.get(Project, 11).name == "Сопровождение образовательных программ"
    assert db.get(Project, 12).name == INTERNAL_PROJECT_NAME
    assert db.get(Project, 99).name == "Внедрение ПРИИСК. Северный банк"
    assert before == {
        model.__tablename__: [tuple(row) for row in db.execute(select(model.__table__))]
        for model in (Task, TaskAssignment, ResourcePlan, TimeEntry, Risk, RiskEvent)
    }
    assert identity_before == [(u.user_id, u.login, u.password_hash, u.full_name.split(maxsplit=1)[1])
                               for u in db.scalars(select(User).order_by(User.user_id))]
    assert upgrade_demo_profiles(db, AS_OF) == {"already_applied": True}


def test_fresh_project_names_describe_the_work_without_company_or_platform_names():
    assert [project[0] for project in PROJECTS] == [
        "Развитие платформы", "Обслуживание клиентов банка", "Сопровождение продаж",
        "Поддержка сотрудников", "Закупки и договорная работа", "Операции интернет-магазина",
        "Документооборот страховой компании", "Производственная база знаний",
        "Логистические операции", "Кадровый сервис", "Сопровождение образовательных программ",
    ]
    assert INTERNAL_PROJECT_NAME == "Внутренние задачи"


def test_all_ninety_surname_roots_are_unique():
    roots = []
    for full_name in demo_names().values():
        surname = full_name.split()[0].casefold().replace("ё", "е")
        roots.append(surname.removesuffix("а"))
    assert len(roots) == len(set(roots)) == 90


def snapshot_except_project_names(db):

    result = {}
    for table in Base.metadata.sorted_tables:
        columns = [column for column in table.c
                   if not (table.name == "projects" and column.name == "name")]
        query = select(*columns).order_by(*table.primary_key.columns)
        if table.name == "system_settings":
            query = query.where(table.c.setting_key != PROJECT_NAMES_MARKER_KEY)
        result[table.name] = [tuple(row) for row in db.execute(query)]
    return result


def test_project_names_upgrade_current_database_preserves_all_other_data(db):
    populate_old_demo(db)
    upgrade_demo_profiles(db, AS_OF)
    for project_id, name in enumerate(PREVIOUS_PROJECT_NAMES, 1):
        db.get(Project, project_id).name = name
    db.get(Project, 12).name = PREVIOUS_INTERNAL_PROJECT_NAME
    db.get(User, 1).full_name = "Имя, изменённое пользователем"
    db.get(Project, 2).description = "Описание, изменённое пользователем"
    db.commit()
    before = snapshot_except_project_names(db)

    assert upgrade_project_names(db) == {"projects_renamed": 12}
    db.commit()
    assert [db.get(Project, i).name for i in range(1, 12)] == [p[0] for p in PROJECTS]
    assert db.get(Project, 12).name == INTERNAL_PROJECT_NAME
    assert snapshot_except_project_names(db) == before
    assert db.scalar(select(SystemSetting.setting_value).where(
        SystemSetting.setting_key == PROJECT_NAMES_MARKER_KEY)) == PROJECT_NAMES_REVISION


    db.get(Project, 1).name = PREVIOUS_PROJECT_NAMES[0]
    db.commit()
    assert upgrade_project_names(db) == {"already_applied": True}
    assert db.get(Project, 1).name == PREVIOUS_PROJECT_NAMES[0]
    assert snapshot_except_project_names(db) == before


def test_seed_upgrades_project_names_when_profile_revision_is_already_current(db, monkeypatch):
    populate_old_demo(db)
    upgrade_demo_profiles(db, AS_OF)
    for project_id, name in enumerate(PREVIOUS_PROJECT_NAMES, 1):
        db.get(Project, project_id).name = name
    db.get(Project, 12).name = PREVIOUS_INTERNAL_PROJECT_NAME
    db.commit()
    before = snapshot_except_project_names(db)
    monkeypatch.setattr(demo, "local_today", lambda: AS_OF)
    monkeypatch.setattr(demo, "build_portfolio", lambda *_args: pytest.fail("Do not rebuild existing data"))

    demo.seed_all(db)
    db.commit()

    assert [db.get(Project, i).name for i in range(1, 12)] == [p[0] for p in PROJECTS]
    assert db.get(Project, 12).name == INTERNAL_PROJECT_NAME
    assert snapshot_except_project_names(db) == before


@pytest.mark.parametrize("prior_names", [
    ORIGINAL_PROJECT_NAMES,
    LEGACY_PROJECT_NAMES,
    PREVIOUS_PROJECT_NAMES,
    [PREVIOUS_PROJECT_NAMES[0], *[f"Внедрение ПРИИСК. {name}" for name in VERSION_ONE_CUSTOMER_NAMES]],
    [PREVIOUS_PROJECT_NAMES[0], *[f"Внедрение ПРИИСК. {name}" for name in VERSION_TWO_CUSTOMER_NAMES]],
], ids=["original", "legacy", "revision-three", "revision-one", "revision-two"])
def test_project_names_upgrade_known_versions_and_preserves_custom_projects(db, prior_names):
    populate_old_demo(db)
    for project_id, name in enumerate(prior_names, 1):
        db.get(Project, project_id).name = name
    db.get(Project, 3).name = "Пользовательское название"

    db.add(Project(project_id=99, name=prior_names[1], manager_id=2,
                   start_date=date(2026, 1, 1), end_date=date(2026, 12, 31)))
    db.commit()
    before = snapshot_except_project_names(db)

    assert upgrade_project_names(db) == {"projects_renamed": 10}
    db.commit()

    for project_id in range(1, 12):
        expected = "Пользовательское название" if project_id == 3 else PROJECTS[project_id - 1][0]
        assert db.get(Project, project_id).name == expected
    assert db.get(Project, 99).name == prior_names[1]
    assert snapshot_except_project_names(db) == before


def test_internal_project_rename_uses_its_admin_manager_not_a_fixed_project_id(db):
    populate_old_demo(db)
    db.add_all([
        Project(project_id=42, name=PREVIOUS_INTERNAL_PROJECT_NAME, manager_id=1,
                start_date=date(2026, 1, 1), end_date=date(2026, 12, 31)),
        Project(project_id=43, name=PREVIOUS_INTERNAL_PROJECT_NAME, manager_id=200,
                start_date=date(2026, 1, 1), end_date=date(2026, 12, 31)),
    ])
    db.commit()
    before = snapshot_except_project_names(db)

    assert upgrade_project_names(db) == {"projects_renamed": 12}
    db.commit()

    assert db.get(Project, 42).name == INTERNAL_PROJECT_NAME
    assert db.get(Project, 43).name == PREVIOUS_INTERNAL_PROJECT_NAME
    assert snapshot_except_project_names(db) == before


@pytest.mark.parametrize("dataset, login", [(None, "admin"), ("custom", "admin"), ("priisk-2026-2", "owner")])
def test_project_names_upgrade_skips_unidentified_databases(db, dataset, login):
    db.add(User(user_id=1, login=login, full_name="Собственный Пользователь", role="admin", password_hash="keep"))
    if dataset is not None:
        db.add(SystemSetting(setting_key="demo_dataset_version", setting_value=dataset))
    db.flush()
    db.add(Project(project_id=1, name=PREVIOUS_PROJECT_NAMES[0], manager_id=1,
                   start_date=date(2026, 1, 1), end_date=date(2026, 12, 31)))
    db.commit()
    before = snapshot_except_project_names(db)

    assert upgrade_project_names(db) == {"skipped_non_demo": True}
    assert db.get(Project, 1).name == PREVIOUS_PROJECT_NAMES[0]
    assert snapshot_except_project_names(db) == before
    assert db.scalar(select(SystemSetting).where(SystemSetting.setting_key == PROJECT_NAMES_MARKER_KEY)) is None


def test_profile_upgrade_reuses_internal_project_under_its_previous_name(db):
    populate_old_demo(db)
    db.add(Project(project_id=42, name=PREVIOUS_INTERNAL_PROJECT_NAME, manager_id=1,
                   start_date=date(2026, 1, 1), end_date=date(2026, 12, 31)))
    db.commit()
    task_count = db.scalar(select(func.count()).select_from(Task))

    stats = upgrade_demo_profiles(db, AS_OF)

    assert stats["internal_created"] == 0
    assert stats["internal_project_id"] == 42
    assert db.scalar(select(func.count()).select_from(Project)) == 12
    assert db.scalar(select(func.count()).select_from(Task)) == task_count
