

from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.common.models import Project, ProjectMember, User
from app.common.permissions import get_current_user
from app.core.database import Base, get_db
from app.modules.time_tracking.models import Release, Task, TimeEntry
from app.modules.time_tracking.routers import timesheet


@pytest.fixture
def records():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(
        engine,
        tables=[
            model.__table__
            for model in (User, Project, ProjectMember, Release, Task, TimeEntry)
        ],
    )
    try:
        with Session(engine, expire_on_commit=False) as db:
            users = {
                "admin": User(
                    user_id=1, full_name="Administrator", role="admin",
                    login="admin", password_hash="unused",
                ),
                "manager": User(
                    user_id=2, full_name="First manager", role="manager",
                    login="manager-a", password_hash="unused",
                ),
                "other_manager": User(
                    user_id=3, full_name="Second manager", role="manager",
                    login="manager-b", password_hash="unused",
                ),
                "employee": User(
                    user_id=4, full_name="Shared employee", role="employee",
                    login="employee-a", password_hash="unused",
                ),
                "other_employee": User(
                    user_id=5, full_name="Another employee", role="employee",
                    login="employee-b", password_hash="unused",
                ),
            }
            db.add_all(users.values())
            db.flush()
            for project_id, manager_id in ((101, 2), (102, 3)):
                db.add(Project(
                    project_id=project_id, manager_id=manager_id,
                    name=f"Project {project_id}",
                    start_date=date(2026, 11, 1), end_date=date(2026, 11, 30),
                ))
            db.flush()
            db.add_all([
                ProjectMember(project_id=101, user_id=4),
                ProjectMember(project_id=102, user_id=4),
                ProjectMember(project_id=101, user_id=5),
            ])
            for task_id, project_id in ((201, 101), (202, 102)):
                db.add(Task(
                    task_id=task_id, project_id=project_id, name=f"Task {task_id}",
                    start_date=date(2026, 11, 1), due_date=date(2026, 11, 30),
                ))
            db.flush()
            db.add_all([
                TimeEntry(entry_id=1001, user_id=4, task_id=201,
                          work_date=date(2026, 11, 10), hours=3),
                TimeEntry(entry_id=1002, user_id=5, task_id=201,
                          work_date=date(2026, 11, 11), hours=2),
                TimeEntry(entry_id=1003, user_id=4, task_id=202,
                          work_date=date(2026, 11, 11), hours=4),
                TimeEntry(entry_id=1004, user_id=1, task_id=202,
                          work_date=date(2026, 11, 12), hours=1),
            ])
            db.commit()
            yield db, users
    finally:
        engine.dispose()


@pytest.fixture
def get_entries(records, monkeypatch):
    db, users = records


    monkeypatch.setattr(timesheet, "audit", lambda *_args, **_kwargs: None)
    app = FastAPI()
    app.include_router(timesheet.router)

    def test_db():
        yield db

    app.dependency_overrides[get_db] = test_db
    with TestClient(app) as client:
        def request(role, **params):
            app.dependency_overrides[get_current_user] = lambda: users[role]
            return client.get("/api/time-entries", params=params)

        yield request


@pytest.mark.parametrize(
    "role, expected_ids, expected_total",
    [
        ("admin", {1001, 1002, 1003, 1004}, 10),
        ("employee", {1001, 1003}, 7),
        ("manager", {1001, 1002}, 5),
    ],
)
def test_default_visibility_without_user_filter(
    get_entries, role, expected_ids, expected_total,
):
    response = get_entries(role)

    assert response.status_code == 200
    payload = response.json()
    assert {row["entry_id"] for row in payload["items"]} == expected_ids
    assert payload["total"] == expected_total
    assert all(row["user_name"] for row in payload["items"])


@pytest.mark.parametrize(
    "role, expected_ids, expected_total",
    [
        ("admin", {1001, 1003}, 7),
        ("employee", {1001, 1003}, 7),
        ("manager", {1001}, 3),
    ],
)
def test_explicit_user_filter_preserves_role_scope(
    get_entries, role, expected_ids, expected_total,
):

    response = get_entries(role, user_id=4)

    assert response.status_code == 200
    payload = response.json()
    assert {row["entry_id"] for row in payload["items"]} == expected_ids
    assert payload["total"] == expected_total


@pytest.mark.parametrize(
    "role, params",
    [
        ("employee", {"user_id": 5}),
        ("manager", {"project_id": 102}),
    ],
)
def test_forbidden_filters_cannot_expand_access(get_entries, role, params):
    response = get_entries(role, **params)

    assert response.status_code == 403
