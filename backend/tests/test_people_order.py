from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.common.models import Project, ProjectMember, User
from app.common.routers import projects, users
from app.common.schemas import UserCreate, UserUpdate
from app.common.services.people import name_sort_key
from app.core.database import Base
from app.modules.time_tracking.models import Task, TaskAssignment
from app.modules.time_tracking.routers import resources
from app.modules.time_tracking.services.task_view import task_rows


@pytest.fixture
def records(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(users, "audit", lambda *_args: None)
    monkeypatch.setattr(resources, "audit", lambda *_args: None)
    monkeypatch.setattr(users, "hash_password", lambda _password: "test-hash")
    with Session(engine, expire_on_commit=False) as db:
        people = [
            User(user_id=1, login="admin", full_name="Яковлев Андрей Игоревич", role="admin", password_hash="test"),
            User(user_id=2, login="a", full_name="Жуков Илья Сергеевич", role="employee", password_hash="test"),
            User(user_id=3, login="b", full_name="Ёлкин Роман Петрович", role="employee", password_hash="test"),
            User(user_id=4, login="c", full_name="Егоров Пётр Андреевич", role="employee", password_hash="test"),
            User(user_id=5, login="d", full_name="Андреев Павел Николаевич", role="employee", password_hash="test"),
        ]
        db.add_all(people)
        db.flush()
        project = Project(name="Test", manager_id=1, start_date=date(2026, 11, 1), end_date=date(2026, 11, 30))
        db.add(project)
        db.flush()
        task = Task(project_id=project.project_id, name="Test task", start_date=project.start_date, due_date=project.end_date)
        db.add(task)
        db.flush()
        for person in people:
            db.add(ProjectMember(project_id=project.project_id, user_id=person.user_id))
            db.add(TaskAssignment(task_id=task.task_id, user_id=person.user_id))
        db.commit()
        yield db, people[0], project, task
    engine.dispose()


def test_all_person_lists_use_surname_order_including_yo(records):
    db, admin, project, task = records
    expected = ["Андреев", "Егоров", "Ёлкин", "Жуков", "Яковлев"]
    result_lists = [
        [p.full_name for p in users.users(user=admin, db=db)],
        [p["full_name"] for p in users.options(user=admin, db=db)],
        [p["full_name"] for p in projects.serialize(db, project)["members"]],
        [p["full_name"] for p in resources.resource_plan(project.project_id, db=db, user=admin)["rows"]],
        [p["full_name"] for p in task_rows(db, [task])[0]["assignments"]],
    ]
    assert all([name.split()[0] for name in names] == expected for names in result_lists)


def test_person_sort_key_normalizes_case_spaces_and_yo():
    assert name_sort_key("  Ёлкин\tРОМАН  Петрович  ", 3) == name_sort_key("елкин роман петрович", 3)
    assert name_sort_key("Иванов Иван Иванович", 1) < name_sort_key("Иванов Иван Иванович", 2)


def test_create_and_update_normalize_whitespace_without_forcing_three_parts(records):
    db, admin, _project, _task = records
    created = users.create(
        UserCreate(login="new-person", full_name="  Иванов  Иван\tИванович ", password="test-password"),
        user=admin, db=db,
    )
    assert created.full_name == "Иванов Иван Иванович"
    updated = users.update(created.user_id, UserUpdate(full_name="  Ли\tМин  "), user=admin, db=db)
    assert updated.full_name == "Ли Мин"
