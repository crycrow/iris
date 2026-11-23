

from datetime import date, datetime, timezone
from io import BytesIO
from xml.etree import ElementTree
from zipfile import ZipFile

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.common.models import Project, ProjectMember, User
from app.common.permissions import get_current_user
from app.core.database import Base, get_db
from app.modules.risk_management.models import Risk, RiskType
from app.modules.risk_management.routers import risks
from app.modules.risk_management.services import queries


@pytest.fixture
def risk_client(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    monkeypatch.setattr(queries, "audit", lambda *_args, **_kwargs: None)
    try:
        with Session(engine, expire_on_commit=False) as db:
            users = {}
            for uid, role, name in (
                (1, "admin", "Администраторов Андрей Петрович"),
                (2, "manager", "Смирнова Анна Сергеевна"),
                (3, "manager", "Орлов Дмитрий Алексеевич"),
                (4, "employee", "Ёлкин Сергей Андреевич"),
                (5, "employee", "Елкин Виктор Иванович"),
            ):
                users[uid] = User(
                    user_id=uid, full_name=name, role=role,
                    login=f"person-{uid}", password_hash="unused",
                )
            db.add_all(users.values())
            db.flush()
            db.add_all([
                Project(project_id=101, manager_id=2, name="Внедрение ПРИИСК. Северный банк",
                        start_date=date(2026, 1, 1), end_date=date(2026, 12, 31)),
                Project(project_id=102, manager_id=3, name="Внедрение ПРИИСК. Южный банк",
                        start_date=date(2026, 1, 1), end_date=date(2026, 12, 31)),
            ])
            db.flush()
            db.add_all([
                ProjectMember(project_id=101, user_id=2),
                ProjectMember(project_id=101, user_id=4),
                ProjectMember(project_id=102, user_id=3),
                ProjectMember(project_id=102, user_id=5),
                RiskType(risk_type_id=11, code="custom:load:11", name="Перегрузка сотрудника",
                         risk_group="Трудозатраты", object_kind="employee", metric="load",
                         condition_op="gt", threshold=100, severity="high"),
                RiskType(risk_type_id=12, code="custom:delay:12", name="Задержка задач",
                         risk_group="Сроки", object_kind="project", metric="delta_t",
                         condition_op="gt", threshold=5, severity="medium"),
            ])
            db.flush()
            for rid, type_id, pid, subject_id in (
                (301, 11, 101, 4),
                (302, 12, 101, 4),
                (303, 11, 102, 5),
                (304, 11, None, 4),
                (305, 11, None, 5),
                (306, 11, 101, None),
                (307, 11, 102, 4),
                (308, 11, None, 3),
            ):
                db.add(Risk(
                    risk_id=rid, risk_type_id=type_id, project_id=pid,
                    subject_user_id=subject_id, responsible_id=2 if pid == 101 else 3,
                    description=f"Уникальное описание риска {rid}",
                    status="new", detected_at=datetime(2026, 11, 10, 12, tzinfo=timezone.utc),
                ))
            db.commit()
            app = FastAPI()
            app.include_router(risks.router)
            app.dependency_overrides[get_db] = lambda: db
            with TestClient(app) as client:
                def request(user_id=1, path="/api/risks", **params):
                    app.dependency_overrides[get_current_user] = lambda: users[user_id]
                    return client.get(path, params=params)

                yield request
    finally:
        engine.dispose()


def ids(response):
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["counts"]["total"] == len(payload["items"])
    return {item["risk_id"] for item in payload["items"]}


@pytest.mark.parametrize("params, expected", [
    ({"object_search": "  СеВеРнЫй   еЛКИН  "}, {301, 302}),
    ({"object_search": "ЁЛКИН", "risk_type_id": 11}, {301, 303, 304, 305, 307}),
    ({"object_search": "северный елкин", "risk_type_id": 12}, {302}),
    ({"object_search": "северный", "risk_type_id": 11}, {301, 306}),
    ({"object_search": "несуществующий объект", "risk_type_id": 11}, set()),
])
def test_object_search_normalizes_case_spaces_and_yo_and_intersects_type(risk_client, params, expected):
    assert ids(risk_client(**params)) == expected


@pytest.mark.parametrize("user_id, expected", [
    (1, {301, 303, 304, 305, 307}),
    (2, {301, 304}),
    (4, {301, 304}),
])
def test_search_and_type_preserve_visibility(risk_client, user_id, expected):
    assert ids(risk_client(user_id, object_search="елкин", risk_type_id=11)) == expected


def spreadsheet_rows(content):

    namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with ZipFile(BytesIO(content)) as archive:
        strings = [
            "".join(item.itertext())
            for item in ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
        ]
        sheet = ElementTree.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        result = []
        for row in sheet.findall("x:sheetData/x:row", namespace):
            if int(row.attrib["r"]) < 5:
                continue
            values = [""] * 8
            for cell in row.findall("x:c", namespace):
                value = cell.find("x:v", namespace)
                if value is not None:
                    text = value.text or ""
                    values[ord(cell.attrib["r"][0]) - ord("A")] = (
                        strings[int(text)] if cell.attrib.get("t") == "s" else text
                    )
            result.append(values)
    return result


@pytest.mark.parametrize("user_id, params, expected", [
    (1, {"object_search": "ЕЛКИН", "risk_type_id": 11}, {301, 303, 304, 305, 307}),
    (2, {"object_search": "елкин", "risk_type_id": 11}, {301, 304}),
    (2, {"object_search": "северный", "risk_type_id": 12}, {302}),
    (2, {"object_search": "южный", "risk_type_id": 11}, set()),
])
def test_xlsx_contains_exactly_filtered_register_rows(risk_client, user_id, params, expected):
    register = risk_client(user_id, **params)
    assert ids(register) == expected
    response = risk_client(user_id, "/api/risks/export.xlsx", **params)
    assert response.status_code == 200
    assert "spreadsheetml.sheet" in response.headers["content-type"]
    rows = spreadsheet_rows(response.content)
    items = register.json()["items"]
    assert [row[7] for row in rows] == [item["description"] for item in items]
    assert [row[0] for row in rows] == [item["type_name"] for item in items]
    assert [row[3] for row in rows] == [item["subject_name"] or "" for item in items]


@pytest.mark.parametrize("extension", ["xlsx", "pdf"])
def test_employee_cannot_export_even_own_filtered_risks(risk_client, extension):
    response = risk_client(4, f"/api/risks/export.{extension}", object_search="елкин", risk_type_id=11)
    assert response.status_code == 403


@pytest.mark.parametrize("path", ["/api/risks", "/api/risks/export.xlsx", "/api/risks/export.pdf"])
def test_explicit_project_filter_cannot_expand_manager_access(risk_client, path):
    response = risk_client(2, path, project_id=102, object_search="южный", risk_type_id=11)
    assert response.status_code == 403
