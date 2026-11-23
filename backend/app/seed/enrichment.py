from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.models import Project, ProjectMember, SystemSetting, User
from app.modules.risk_management.models import Risk, RiskType
from app.modules.risk_management.services.engine import run_risk_scan
from app.modules.risk_management.services.lifecycle import add_event, transition
from app.modules.risk_management.services.readers import load_context
from app.modules.risk_management.services.rules import deadlines, estimation, load
from app.modules.time_tracking.models import (
    MetricSnapshot,
    ResourcePlan,
    Task,
    TaskActivity,
    TaskAssignment,
    TimeEntry,
)
from app.modules.time_tracking.services.snapshots import compute_and_store_snapshot
from app.modules.time_tracking.services.working_calendar import read_calendar

REVISION = "priisk-2026-4"


def latest_work_day(db: Session, as_of: date) -> date:
    calendars = [
        read_calendar(db, pid) for pid in db.scalars(select(Project.project_id))
    ]
    for offset in range(60):
        candidate = as_of - timedelta(days=offset)
        if any(calendar.get(candidate, 0) > 0 for calendar in calendars):
            return candidate
    raise ValueError("В демонстрационном календаре нет рабочих дней")


def assign_responsible(db: Session) -> int:
    projects = {p.project_id: p for p in db.scalars(select(Project))}
    users = {u.user_id: u for u in db.scalars(select(User))}
    tasks = {t.task_id: t for t in db.scalars(select(Task))}
    assignments = list(db.scalars(select(TaskAssignment)))
    count = 0
    for risk in db.scalars(select(Risk).where(Risk.responsible_id.is_(None))):
        project = projects.get(risk.project_id) if risk.project_id is not None else None
        candidates = [
            a.user_id
            for a in assignments
            if a.task_id == risk.task_id
            and users[a.user_id].role == "employee"
            and not users[a.user_id].is_blocked
        ]
        if candidates:
            responsible = min(candidates)
        elif project:
            responsible = project.manager_id
        else:
            subject_projects = {
                tasks[a.task_id].project_id
                for a in assignments
                if a.user_id == risk.subject_user_id
            }
            suitable = [projects[pid] for pid in sorted(subject_projects)]
            responsible = (
                suitable[0].manager_id
                if suitable
                else min(u.user_id for u in users.values() if u.role == "admin")
            )
        risk.responsible_id = responsible
        add_event(db, risk, None, "assigned", {"responsible_id": responsible})
        if risk.status == "new":
            transition(db, risk, "reviewing", None)
        count += 1
    db.flush()
    return count


def restore_risk_evidence(db: Session, as_of: date) -> int:
    projects = list(db.scalars(select(Project.project_id)))
    current_week = as_of - timedelta(days=as_of.weekday())
    weeks = sorted(
        set(
            db.scalars(
                select(MetricSnapshot.week_start).where(
                    MetricSnapshot.week_start < current_week
                )
            )
        )
    )
    types = list(db.scalars(select(RiskType).where(RiskType.is_active.is_(True))))
    risks = {
        (r.risk_type_id, r.project_id, r.task_id, r.subject_user_id): r
        for r in db.scalars(select(Risk))
        if r.measured_value is not None
        and not any(e.event_type == "created_manual" for e in r.events)
    }
    restored: set[int] = set()
    for week in weeks:
        observed = week + timedelta(days=6)
        context = load_context(db, observed, projects)
        historical_tasks = {}
        for task_id, task in context["tasks"].items():
            rows = context["histories"].get((task.project_id, task_id, None), [])
            if not rows or rows[0]["week_start"] != week:
                continue
            row = rows[0]
            bac, ev, ac = (float(row[key] or 0) for key in ("bac", "ev", "ac"))
            status = "done" if bac and ev >= bac else "dev" if ev or ac else "todo"
            historical_tasks[task_id] = SimpleNamespace(
                task_id=task_id,
                project_id=task.project_id,
                name=task.name,
                is_milestone=task.is_milestone,
                status=status,
            )
        context["tasks"] = historical_tasks
        context["active_users"] = {
            uid
            for (pid, tid, uid), rows in context["histories"].items()
            if pid
            and uid
            and rows
            and rows[0]["week_start"] == week
            and float(rows[0]["w"] or 0) > 0
        }
        findings = []
        for rt in types:
            if rt.object_kind:
                continue
            if rt.rule_code in (
                "task_overdue",
                "task_delay",
                "project_overdue",
                "task_idle",
            ):
                findings.extend(deadlines.evaluate(rt, context))
            elif rt.rule_code in ("task_overrun", "project_overrun"):
                findings.extend(estimation.evaluate(rt, context))
            elif rt.rule_code in ("overload", "underload"):
                findings.extend(load.evaluate(rt, context))
        for finding in findings:
            key = tuple(
                finding[k]
                for k in ("risk_type_id", "project_id", "task_id", "subject_user_id")
            )
            risk = risks.get(key)
            if (
                risk is None
                or risk.risk_id in restored
                or observed >= risk.detected_at.date()
            ):
                continue
            risk.detected_at = datetime.combine(
                observed, datetime.min.time(), timezone.utc
            ) + timedelta(hours=18)
            event = add_event(
                db,
                risk,
                None,
                "history_restored",
                {
                    "comment": "Дата основания восстановлена по сохранённым недельным показателям",
                    "week_start": week.isoformat(),
                    "measured_value": float(finding["measured_value"]),
                    "source": "metric_snapshots",
                },
            )
            event.event_at = datetime.now(timezone.utc)
            restored.add(risk.risk_id)
    db.flush()
    return len(restored)


def enrich_demo(db: Session, as_of: date) -> dict[str, int]:
    marker = db.scalar(
        select(SystemSetting).where(
            SystemSetting.setting_key == "demo_enrichment_version"
        )
    )
    if marker and marker.setting_value == REVISION:
        return {"already_applied": 1}
    work_day = latest_work_day(db, as_of)
    stats: dict[str, int] = defaultdict(int)
    users = {u.user_id: u for u in db.scalars(select(User))}
    projects = {p.project_id: p for p in db.scalars(select(Project))}
    tasks = {t.task_id: t for t in db.scalars(select(Task))}
    assignments = list(db.scalars(select(TaskAssignment)))
    entries = list(db.scalars(select(TimeEntry)))
    members = list(db.scalars(select(ProjectMember)))
    parents = {t.parent_task_id for t in tasks.values() if t.parent_task_id}
    actual: dict[int, Decimal] = defaultdict(Decimal)
    daily: dict[tuple[int, date], Decimal] = defaultdict(Decimal)
    for entry in entries:
        actual[entry.task_id] += entry.hours
        daily[entry.user_id, entry.work_date] += entry.hours
    for member in members:
        if (
            users[member.user_id].role != "manager"
            or projects[member.project_id].manager_id == member.user_id
        ):
            continue
        assert not any(
            a.user_id == member.user_id
            and tasks[a.task_id].project_id == member.project_id
            for a in assignments
        )
        assert not any(
            e.user_id == member.user_id
            and tasks[e.task_id].project_id == member.project_id
            for e in entries
        )
        for old_snapshot in db.scalars(
            select(MetricSnapshot).where(
                MetricSnapshot.project_id == member.project_id,
                MetricSnapshot.user_id == member.user_id,
            )
        ):
            assert all(
                not getattr(old_snapshot, field)
                for field in ("bac", "pv", "ev", "ac", "w", "k")
            )
            db.delete(old_snapshot)
            stats["empty_snapshots_removed"] += 1
        db.delete(member)
        stats["foreign_members_removed"] += 1
    db.flush()
    synthetic = lambda t: t.description.startswith(
        "Подготовить результат и согласовать его с командой"
    ) or t.name.startswith("Координация поставки и работа с заказчиком")
    started: set[int] = set()
    for project in projects.values():
        future = sorted(
            (
                t
                for t in tasks.values()
                if t.project_id == project.project_id
                and t.start_date > as_of
                and t.task_id not in parents
                and not t.is_milestone
                and t.status != "cancelled"
                and synthetic(t)
            ),
            key=lambda t: (t.start_date, t.due_date, t.task_id),
        )
        for task in future[:-3]:
            old = task.start_date
            task.start_date = work_day
            started.add(task.task_id)
            db.add(
                TaskActivity(
                    task_id=task.task_id,
                    change_type="start_date",
                    old_value=old.isoformat(),
                    new_value=work_day.isoformat(),
                )
            )
            db.add(
                TaskActivity(
                    task_id=task.task_id,
                    change_type="comment",
                    new_value="Начата предварительная подготовка материалов и сценариев следующего этапа. Срок поставки сохранён.",
                )
            )
            if task.parent_task_id:
                parent = tasks[task.parent_task_id]
                parent.start_date = min(parent.start_date, work_day)
            stats["tasks_started_early"] += 1
    plans = list(db.scalars(select(ResourcePlan)))
    month = work_day.replace(day=1)
    for assignment in assignments:
        if assignment.task_id not in started:
            continue
        assignment_plans = [
            p for p in plans if p.assignment_id == assignment.assignment_id
        ]
        if any(p.plan_month == month and p.planned_hours > 0 for p in assignment_plans):
            continue
        future_rows = sorted(
            (p for p in assignment_plans if p.plan_month > month),
            key=lambda p: p.plan_month,
        )
        total = sum((p.planned_hours for p in future_rows), Decimal(0))
        remaining = min(Decimal(8), total)
        allocated = remaining
        for row in future_rows:
            taken = min(row.planned_hours, remaining)
            row.planned_hours -= taken
            remaining -= taken
            if not remaining:
                break
        if allocated:
            existing = next(
                (p for p in assignment_plans if p.plan_month == month), None
            )
            if existing is None:
                existing = ResourcePlan(
                    assignment_id=assignment.assignment_id,
                    plan_month=month,
                    planned_hours=allocated,
                )
                db.add(existing)
                plans.append(existing)
            else:
                existing.planned_hours += allocated
            stats["plans_rebalanced"] += 1
    assigned_ids = {a.task_id for a in assignments}
    for task in tasks.values():
        if (
            task.task_id in parents
            or task.is_milestone
            or task.status in ("done", "cancelled")
            or task.start_date > as_of
            or task.task_id in assigned_ids
        ):
            continue
        candidates = [
            m.user_id
            for m in members
            if m.project_id == task.project_id
            and users[m.user_id].role == "employee"
            and not users[m.user_id].is_blocked
        ]
        if not candidates:
            continue
        uid = min(
            candidates,
            key=lambda uid: (sum(a.user_id == uid for a in assignments), uid),
        )
        assignment = TaskAssignment(task_id=task.task_id, user_id=uid)
        db.add(assignment)
        db.flush()
        assignments.append(assignment)
        stats["missing_assignments_added"] += 1
    calendars = {pid: read_calendar(db, pid) for pid in projects}
    by_user: dict[int, list[TaskAssignment]] = defaultdict(list)
    for assignment in assignments:
        task = tasks[assignment.task_id]
        if (
            task.task_id not in parents
            and not task.is_milestone
            and task.status not in ("done", "cancelled")
            and task.start_date <= work_day
            and calendars[task.project_id].get(work_day, 0) > 0
        ):
            by_user[assignment.user_id].append(assignment)
    new_fact: dict[int, Decimal] = defaultdict(Decimal)
    for uid, rows in by_user.items():
        rows.sort(key=lambda a: (actual[a.task_id] > 0, a.task_id))
        units = int(max(Decimal(0), Decimal(8) - daily[uid, work_day]) * 2)
        if not units:
            continue
        assert len([a for a in rows if a.task_id in started]) <= units, (
            uid,
            len(rows),
            units,
        )
        for i, assignment in enumerate(rows[:units]):
            hours = (
                Decimal(
                    units // min(len(rows), units) + (i < units % min(len(rows), units))
                )
                / 2
            )
            task = tasks[assignment.task_id]
            db.add(
                TimeEntry(
                    user_id=uid,
                    task_id=task.task_id,
                    work_date=work_day,
                    hours=hours,
                    comment=(
                        "Предварительная подготовка сценариев и материалов этапа"
                        if task.task_id in started
                        else "Выполнение текущих работ и согласование результата"
                    ),
                )
            )
            new_fact[task.task_id] += hours
            stats["entries_added"] += 1
    assignment_tasks = {a.assignment_id: a.task_id for a in assignments}
    task_bac: dict[int, Decimal] = defaultdict(Decimal)
    for plan in plans:
        task_bac[assignment_tasks[plan.assignment_id]] += plan.planned_hours
    for task_id, hours in new_fact.items():
        task = tasks[task_id]
        if task_id in started:
            old_status = task.status
            task.status = "dev"
            bac = task_bac[task_id]
            task.progress_pct = (
                min(10, max(1, round(float(hours / bac * 100)))) if bac else 5
            )
            db.add(
                TaskActivity(
                    task_id=task_id,
                    change_type="status",
                    old_value=old_status,
                    new_value="dev",
                )
            )
    overtime: list[tuple[int, int, date]] = []
    for (uid, day), hours in sorted(daily.items()):
        if (
            hours != 8
            or users[uid].role != "employee"
            or (day.toordinal() + uid * 13) % 71
        ):
            continue
        source = next(e for e in entries if e.user_id == uid and e.work_date == day)
        db.add(
            TimeEntry(
                user_id=uid,
                task_id=source.task_id,
                work_date=day,
                hours=1,
                comment="Дополнительный час на устранение замечаний перед согласованием результата",
            )
        )
        overtime.append((uid, source.task_id, day))
        stats["nine_hour_days"] += 1
    current_week = as_of - timedelta(days=as_of.weekday())
    for snapshot in db.scalars(
        select(MetricSnapshot).where(MetricSnapshot.week_start < current_week)
    ):
        end = snapshot.week_start + timedelta(days=6)
        if snapshot.user_id is None and snapshot.project_id is not None:
            extra = sum(
                1
                for _, tid, day in overtime
                if day <= end
                and tasks[tid].project_id == snapshot.project_id
                and (snapshot.task_id is None or snapshot.task_id == tid)
            )
            snapshot.ac += extra
        elif (
            snapshot.project_id is None
            and snapshot.user_id is not None
            and snapshot.u_fact is not None
        ):
            extra = sum(
                1
                for uid, _, day in overtime
                if uid == snapshot.user_id and snapshot.week_start <= day <= end
            )
            project_id = min(
                (m.project_id for m in members if m.user_id == snapshot.user_id),
                default=None,
            )
            if extra and project_id is not None:
                working_days = sum(
                    calendars[project_id].get(
                        snapshot.week_start + timedelta(days=d), 0
                    )
                    > 0
                    for d in range(7)
                )
                if working_days:
                    snapshot.u_fact = (
                        float(snapshot.u_fact) + extra / (working_days * 8) * 100
                    )
    db.flush()
    stats["risk_dates_restored"] = restore_risk_evidence(db, as_of)
    compute_and_store_snapshot(db, as_of)
    run_risk_scan(db, as_of, None)
    stats["risks_assigned"] = assign_responsible(db)
    if marker is None:
        db.add(
            SystemSetting(
                setting_key="demo_enrichment_version",
                setting_value=REVISION,
                description="Адресное дополнение демонстрационных данных",
            )
        )
    else:
        marker.setting_value = REVISION
    db.flush()
    return dict(stats)
