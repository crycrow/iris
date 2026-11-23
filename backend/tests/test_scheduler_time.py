from datetime import datetime, date
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from apscheduler.schedulers.background import BackgroundScheduler

from app.common.models import SystemSetting, User
from app.common.permissions import get_current_user
from app.common.routers import settings as settings_router
from app.core.database import get_db
from app.core import scheduler


@pytest.fixture
def settings_client(monkeypatch):
    engine = create_engine('sqlite:///:memory:', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    SystemSetting.__table__.create(engine)
    calls = []
    monkeypatch.setattr(scheduler, 'reschedule', lambda: calls.append(True))
    with Session(engine) as db:
        db.add_all([SystemSetting(setting_key=key, setting_value=value) for key, value in
                    [('scheduler_hour', '23'), ('scheduler_minute', '55'), ('scheduler_day', 'sun'), ('token_minutes', '480')]])
        db.commit()
        app = FastAPI()
        app.include_router(settings_router.router)
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_current_user] = lambda: User(user_id=1, role='admin')
        with TestClient(app) as client:
            yield client, db, calls
    engine.dispose()


def test_combined_time_round_trip_saves_all_parts_once(settings_client):
    client, db, calls = settings_client
    values = {s['setting_key']: s['setting_value'] for s in client.get('/api/settings').json()}
    assert values['scheduler_time'] == '23:55:00'
    assert 'scheduler_hour' not in values
    response = client.put('/api/settings/scheduler_time', json={'setting_value': '07:09:13'})
    assert response.status_code == 200
    assert calls == [True]
    values = {s.setting_key: s.setting_value for s in db.scalars(select(SystemSetting))}
    assert [values[key] for key in ('scheduler_hour', 'scheduler_minute', 'scheduler_second')] == ['7', '9', '13']
    values = {s['setting_key']: s['setting_value'] for s in client.get('/api/settings').json()}
    assert values['scheduler_time'] == '07:09:13'


@pytest.mark.parametrize('invalid', ['24:00:00', '12:60:00', '12:30:60', '7:09:13', '12:30', 'test'])
def test_invalid_time_does_not_partially_save(settings_client, invalid):
    client, db, calls = settings_client
    assert client.put('/api/settings/scheduler_time', json={'setting_value': invalid}).status_code == 422
    assert not calls
    assert db.scalar(select(SystemSetting.setting_value).where(SystemSetting.setting_key == 'scheduler_hour')) == '23'


def test_scheduler_honors_seconds_and_midnight_grace():
    tz = ZoneInfo('Europe/Moscow')
    assert scheduler.scheduled_date(datetime(2026, 11, 15, 23, 55, 12, tzinfo=tz), 'sun', 23, 55, 13) is None
    assert scheduler.scheduled_date(datetime(2026, 11, 15, 23, 55, 13, tzinfo=tz), 'sun', 23, 55, 13) == date(2026, 11, 15)
    assert scheduler.grace_seconds(23, 59, 59) == 1


@pytest.mark.parametrize('hour, minute, second', [(0, 0, 0), (7, 9, 13), (23, 59, 59)])
def test_reschedule_builds_cron_with_every_time_component(monkeypatch, hour, minute, second):
    engine = create_engine('sqlite:///:memory:')
    SystemSetting.__table__.create(engine)
    sessions = sessionmaker(bind=engine)
    try:
        with sessions.begin() as db:
            db.add_all([
                SystemSetting(setting_key=key, setting_value=str(value))
                for key, value in [('scheduler_day', 'mon'), ('scheduler_hour', hour),
                                   ('scheduler_minute', minute), ('scheduler_second', second)]
            ])
        isolated_scheduler = BackgroundScheduler(timezone='Europe/Moscow')
        monkeypatch.setattr(scheduler, 'SessionLocal', sessions)
        monkeypatch.setattr(scheduler, 'scheduler', isolated_scheduler)
        scheduler.reschedule()
        job = isolated_scheduler.get_job('weekly_analysis')
        assert job.kwargs == {'day': 'mon', 'hour': hour, 'minute': minute, 'second': second}
        tz = ZoneInfo('Europe/Moscow')
        assert job.trigger.get_next_fire_time(None, datetime(2026, 11, 8, 23, 59, 59, tzinfo=tz)) == datetime(
            2026, 11, 9, hour, minute, second, tzinfo=tz,
        )
    finally:
        engine.dispose()
