from datetime import date

import pytest
from sqlalchemy import delete
from app.common.models import Project

from app.modules.time_tracking.models import Task, TaskAssignment, TimeEntry
from app.modules.time_tracking.services.timesheet import previous_week_status
from test_time_entry_visibility import records


def assign_employee(db):
    TaskAssignment.__table__.create(db.get_bind())
    db.add(TaskAssignment(task_id=201, user_id=4))
    db.flush()


def test_reminder_starts_after_completed_week_and_links_exact_dates(records):
    db, users = records
    assign_employee(db)
    db.get(Task, 201).start_date = date(2026, 11, 2)
    db.flush()
    assert not previous_week_status(db, users['employee'], date(2026, 11, 8))['missing']
    status = previous_week_status(db, users['employee'], date(2026, 11, 9))
    assert status == {'from': date(2026, 11, 2), 'to': date(2026, 11, 8), 'hours': 0, 'missing': True}


def test_current_week_entry_does_not_hide_missing_previous_week(records):
    db, users = records
    assign_employee(db)
    db.execute(delete(TimeEntry).where(TimeEntry.user_id == 4))
    db.add(TimeEntry(user_id=4, task_id=201, work_date=date(2026, 11, 16), hours=8))
    db.flush()
    assert previous_week_status(db, users['employee'], date(2026, 11, 16))['missing']


def test_recorded_previous_week_clears_reminder(records):
    db, users = records
    assign_employee(db)
    status = previous_week_status(db, users['employee'], date(2026, 11, 16))
    assert status['hours'] == 7
    assert not status['missing']


def test_manager_reminded_unassigned_people_not_reminded(records):
    db, users = records
    assign_employee(db)
    db.get(Project, 101).status = 'active'
    db.flush()
    assert previous_week_status(db, users['manager'], date(2026, 11, 16))['missing']
    assert not previous_week_status(db, users['admin'], date(2026, 11, 16))['missing']
    assert not previous_week_status(db, users['other_employee'], date(2026, 11, 23))['missing']


@pytest.mark.parametrize('role', ['employee', 'manager', 'admin'])
def test_all_roles_warn_on_eighth_day_and_clear_after_previous_week_entry(records, role):
    db, users = records
    assign_employee(db)
    user = users[role]
    if role != 'employee':
        db.add(TaskAssignment(task_id=201, user_id=user.user_id))
    db.get(Task, 201).start_date = date(2026, 11, 2)
    db.flush()
    assert not previous_week_status(db, user, date(2026, 11, 8))['missing']
    assert previous_week_status(db, user, date(2026, 11, 9))['missing']
    db.add(TimeEntry(user_id=user.user_id, task_id=201, work_date=date(2026, 11, 9), hours=8))
    db.flush()
    assert previous_week_status(db, user, date(2026, 11, 9))['missing']
    db.add(TimeEntry(user_id=user.user_id, task_id=201, work_date=date(2026, 11, 6), hours=8))
    db.flush()
    assert not previous_week_status(db, user, date(2026, 11, 9))['missing']


def test_admin_managing_project_is_reminded_without_task_assignment(records):
    db, users = records
    assign_employee(db)
    project = db.get(Project, 101)
    project.manager_id = users['admin'].user_id
    project.status = 'active'
    db.execute(delete(TimeEntry).where(TimeEntry.user_id == users['admin'].user_id))
    db.flush()
    assert previous_week_status(db, users['admin'], date(2026, 11, 16))['missing']
