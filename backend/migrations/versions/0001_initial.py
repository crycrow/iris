from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:

    op.create_table(
        "risk_types",
        sa.Column("risk_type_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=250), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("risk_group", sa.String(length=100), nullable=False),
        sa.Column("metric", sa.String(length=64), nullable=False),
        sa.Column("condition_op", sa.String(length=4), nullable=False),
        sa.Column("threshold", sa.Numeric(precision=14, scale=6), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.CheckConstraint("condition_op IN ('gt','gte','lt','lte')"),
        sa.CheckConstraint("severity IN ('medium','high','critical')"),
        sa.PrimaryKeyConstraint("risk_type_id"),
        sa.UniqueConstraint("code"),
    )
    op.create_table(
        "system_settings",
        sa.Column("setting_id", sa.Integer(), nullable=False),
        sa.Column("setting_key", sa.String(length=100), nullable=False),
        sa.Column("setting_value", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("setting_id"),
        sa.UniqueConstraint("setting_key"),
    )
    op.create_table(
        "users",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("job_title", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("login", sa.String(length=100), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_blocked", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "role IN ('admin','manager','employee')", name="ck_users_role"
        ),
        sa.PrimaryKeyConstraint("user_id"),
        sa.UniqueConstraint("login"),
    )
    op.create_table(
        "projects",
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("manager_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=250), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("planned_hours", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.CheckConstraint(
            "status IN ('planned','active','completed','cancelled')",
            name="ck_projects_status",
        ),
        sa.CheckConstraint("end_date >= start_date", name="ck_projects_dates"),
        sa.CheckConstraint("planned_hours >= 0", name="ck_projects_hours"),
        sa.ForeignKeyConstraint(["manager_id"], ["users.user_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("project_id"),
    )
    op.create_index(
        op.f("ix_projects_manager_id"), "projects", ["manager_id"], unique=False
    )
    op.create_table(
        "risk_type_params",
        sa.Column("param_id", sa.Integer(), nullable=False),
        sa.Column("risk_type_id", sa.Integer(), nullable=False),
        sa.Column("param_name", sa.String(length=64), nullable=False),
        sa.Column("param_value", sa.Numeric(precision=14, scale=6), nullable=False),
        sa.ForeignKeyConstraint(
            ["risk_type_id"], ["risk_types.risk_type_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("param_id"),
        sa.UniqueConstraint("risk_type_id", "param_name"),
    )
    op.create_table(
        "sessions",
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("session_id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        op.f("ix_sessions_expires_at"), "sessions", ["expires_at"], unique=False
    )
    op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"], unique=False)
    op.create_table(
        "calendars",
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("calendar_date", sa.Date(), nullable=False),
        sa.Column("working_hours", sa.Numeric(precision=4, scale=2), nullable=False),
        sa.CheckConstraint("working_hours >= 0 AND working_hours <= 24"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.project_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("project_id", "calendar_date"),
    )
    op.create_table(
        "project_members",
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.project_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("project_id", "user_id"),
    )
    op.create_table(
        "releases",
        sa.Column("release_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("release_date", sa.Date(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.project_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("release_id"),
    )
    op.create_index(
        op.f("ix_releases_project_id"), "releases", ["project_id"], unique=False
    )
    op.create_table(
        "tasks",
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("release_id", sa.Integer(), nullable=True),
        sa.Column("parent_task_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("is_milestone", sa.Boolean(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("progress_pct", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.CheckConstraint("status != 'done' OR progress_pct = 100"),
        sa.CheckConstraint(
            "status IN ('backlog','todo','dev','review','testing','release_wait','done','cancelled')"
        ),
        sa.CheckConstraint("status NOT IN ('backlog','todo') OR progress_pct = 0"),
        sa.CheckConstraint("NOT is_milestone OR start_date = due_date"),
        sa.CheckConstraint("due_date >= start_date"),
        sa.CheckConstraint("progress_pct BETWEEN 0 AND 100"),
        sa.ForeignKeyConstraint(
            ["parent_task_id"], ["tasks.task_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.project_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["release_id"], ["releases.release_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("task_id"),
    )
    op.create_index(
        op.f("ix_tasks_parent_task_id"), "tasks", ["parent_task_id"], unique=False
    )
    op.create_index(op.f("ix_tasks_project_id"), "tasks", ["project_id"], unique=False)
    op.create_table(
        "metric_snapshots",
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("task_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("bac", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("pv", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("ev", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("ac", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("s", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("delta_t", sa.Integer(), nullable=False),
        sa.Column("t_safe", sa.Integer(), nullable=False),
        sa.Column("w", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("m", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("u_plan", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("u_plan_next", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("u_fact", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("k", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.CheckConstraint("project_id IS NOT NULL OR user_id IS NOT NULL"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.project_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.task_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("snapshot_id"),
    )
    op.create_index(
        "ix_snapshots_project_week",
        "metric_snapshots",
        ["project_id", "week_start"],
        unique=False,
    )
    op.create_table(
        "risks",
        sa.Column("risk_id", sa.Integer(), nullable=False),
        sa.Column("risk_type_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("task_id", sa.Integer(), nullable=True),
        sa.Column("responsible_id", sa.Integer(), nullable=True),
        sa.Column("subject_user_id", sa.Integer(), nullable=True),
        sa.Column("measured_value", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("is_viewed", sa.Boolean(), nullable=False),
        sa.Column("is_cause_resolved", sa.Boolean(), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('new','reviewing','in_progress','closed','rejected')"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.project_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["responsible_id"], ["users.user_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["risk_type_id"], ["risk_types.risk_type_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["subject_user_id"], ["users.user_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.task_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("risk_id"),
    )
    op.create_index(op.f("ix_risks_project_id"), "risks", ["project_id"], unique=False)
    op.create_table(
        "task_activity",
        sa.Column("activity_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("change_type", sa.String(length=40), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.task_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("activity_id"),
    )
    op.create_index(
        op.f("ix_task_activity_task_id"), "task_activity", ["task_id"], unique=False
    )
    op.create_table(
        "task_assignments",
        sa.Column("assignment_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.task_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("assignment_id"),
        sa.UniqueConstraint("task_id", "user_id"),
    )
    op.create_index(
        op.f("ix_task_assignments_task_id"),
        "task_assignments",
        ["task_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_task_assignments_user_id"),
        "task_assignments",
        ["user_id"],
        unique=False,
    )
    op.create_table(
        "time_entries",
        sa.Column("entry_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("hours", sa.Numeric(precision=4, scale=2), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.CheckConstraint("hours >= 0.5 AND hours <= 24"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.task_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("entry_id"),
    )
    op.create_index(
        "ix_time_entries_task_date",
        "time_entries",
        ["task_id", "work_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_time_entries_user_id"), "time_entries", ["user_id"], unique=False
    )
    op.create_table(
        "resource_plan",
        sa.Column("assignment_id", sa.Integer(), nullable=False),
        sa.Column("plan_month", sa.Date(), nullable=False),
        sa.Column("planned_hours", sa.Numeric(precision=6, scale=2), nullable=False),
        sa.CheckConstraint(sa.extract("day", sa.column("plan_month")) == 1),
        sa.CheckConstraint("planned_hours >= 0"),
        sa.ForeignKeyConstraint(
            ["assignment_id"], ["task_assignments.assignment_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("assignment_id", "plan_month"),
    )
    op.create_table(
        "risk_actions",
        sa.Column("action_id", sa.Integer(), nullable=False),
        sa.Column("risk_id", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("execution_state", sa.String(length=20), nullable=False),
        sa.CheckConstraint("execution_state IN ('planned','in_progress','done')"),
        sa.ForeignKeyConstraint(["risk_id"], ["risks.risk_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("action_id"),
    )
    op.create_index(
        op.f("ix_risk_actions_risk_id"), "risk_actions", ["risk_id"], unique=False
    )
    op.create_table(
        "risk_events",
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("risk_id", sa.Integer(), nullable=False),
        sa.Column("initiator_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["initiator_id"], ["users.user_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["risk_id"], ["risks.risk_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        op.f("ix_risk_events_risk_id"), "risk_events", ["risk_id"], unique=False
    )
    op.create_index(
        "uq_snapshot_scope_week",
        "metric_snapshots",
        [
            sa.text("coalesce(project_id, 0)"),
            sa.text("coalesce(task_id, 0)"),
            sa.text("coalesce(user_id, 0)"),
            "week_start",
        ],
        unique=True,
    )
    op.create_index(
        "uq_open_risk_object",
        "risks",
        [
            "risk_type_id",
            sa.text("coalesce(project_id, 0)"),
            sa.text("coalesce(task_id, 0)"),
            sa.text("coalesce(subject_user_id, 0)"),
        ],
        unique=True,
        postgresql_where=sa.text("status IN ('new','reviewing','in_progress')"),
        sqlite_where=sa.text("status IN ('new','reviewing','in_progress')"),
    )


def downgrade() -> None:

    op.drop_index(op.f("ix_risk_events_risk_id"), table_name="risk_events")
    op.drop_table("risk_events")
    op.drop_index(op.f("ix_risk_actions_risk_id"), table_name="risk_actions")
    op.drop_table("risk_actions")
    op.drop_table("resource_plan")
    op.drop_index(op.f("ix_time_entries_user_id"), table_name="time_entries")
    op.drop_index("ix_time_entries_task_date", table_name="time_entries")
    op.drop_table("time_entries")
    op.drop_index(op.f("ix_task_assignments_user_id"), table_name="task_assignments")
    op.drop_index(op.f("ix_task_assignments_task_id"), table_name="task_assignments")
    op.drop_table("task_assignments")
    op.drop_index(op.f("ix_task_activity_task_id"), table_name="task_activity")
    op.drop_table("task_activity")
    op.drop_index(op.f("ix_risks_project_id"), table_name="risks")
    op.drop_table("risks")
    op.drop_index("ix_snapshots_project_week", table_name="metric_snapshots")
    op.drop_table("metric_snapshots")
    op.drop_index(op.f("ix_tasks_project_id"), table_name="tasks")
    op.drop_index(op.f("ix_tasks_parent_task_id"), table_name="tasks")
    op.drop_table("tasks")
    op.drop_index(op.f("ix_releases_project_id"), table_name="releases")
    op.drop_table("releases")
    op.drop_table("project_members")
    op.drop_table("calendars")
    op.drop_index(op.f("ix_sessions_user_id"), table_name="sessions")
    op.drop_index(op.f("ix_sessions_expires_at"), table_name="sessions")
    op.drop_table("sessions")
    op.drop_table("risk_type_params")
    op.drop_index(op.f("ix_projects_manager_id"), table_name="projects")
    op.drop_table("projects")
    op.drop_table("users")
    op.drop_table("system_settings")
    op.drop_table("risk_types")
