<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from "vue";
import { api } from "../common/api/client.js";
import { useAuth } from "../common/stores/auth.js";
import {
  list,
  number,
  date,
  taskStatuses,
  projectStatuses,
  severities,
  taskProgress,
  today,
  shiftDate,
} from "../common/utils/format.js";
import Modal from "../common/components/Modal.vue";
import UiIcon from "../common/components/UiIcon.vue";
import { taskHierarchy } from "../modules/time-tracking/taskFilters.js";
import {
  taskGroups,
  leafTasks,
  projectOverview,
  projectTeam,
  weekDates,
  initials,
} from "./dashboardData.js";
const auth = useAuth();
const data = ref({}),
  projects = ref([]),
  risks = ref([]),
  taskLists = ref({});
const busy = ref(true),
  loadError = ref(""),
  incomplete = ref([]),
  selectedDate = ref(""),
  dialog = ref(null);
let alive = true,
  generation = 0;
async function load() {
  const request = ++generation;
  busy.value = true;
  loadError.value = "";
  incomplete.value = [];
  try {
    const [dashboard, registry] = await Promise.all([
      api.get("/dashboard"),
      api.get("/risks"),
    ]);
    const availableProjects = Array.isArray(dashboard.projects)
      ? dashboard.projects
      : list(await api.get("/projects"));
    const loaded = {},
      failed = [];
    let next = 0;

    async function worker() {
      while (
        next < availableProjects.length &&
        alive &&
        request === generation
      ) {
        const project = availableProjects[next++];
        try {
          loaded[project.project_id] = list(
            await api.get(`/projects/${project.project_id}/tasks`),
          );
        } catch {
          loaded[project.project_id] = null;
          failed.push(project.name);
        }
      }
    }
    await Promise.all(
      Array.from({ length: Math.min(4, availableProjects.length) }, worker),
    );
    if (!alive || request !== generation) return;
    data.value = dashboard;
    projects.value = availableProjects;
    risks.value = list(registry);
    taskLists.value = loaded;
    incomplete.value = failed;
    selectedDate.value ||= dashboard.today || today();
  } catch (error) {
    if (alive && request === generation)
      loadError.value = error.message || "Не удалось загрузить рабочую панель";
  } finally {
    if (alive && request === generation) busy.value = false;
  }
}
onMounted(load);
onBeforeUnmount(() => {
  alive = false;
});
const analysisDate = computed(() => data.value.today || today());
const dateLabel = computed(() =>
  new Date(`${analysisDate.value}T12:00:00`).toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "long",
    year: "numeric",
  }),
);
const pageTitle = computed(() =>
  auth.manager ? "Обзор проектов" : "Моя работа",
);
const activeRisks = computed(() =>
  risks.value.filter((risk) => !["closed", "rejected"].includes(risk.status)),
);
const unviewedRisks = computed(() =>
  activeRisks.value.filter((risk) => !risk.is_viewed),
);
const priorityRisks = computed(() =>
  [...activeRisks.value].sort(
    (a, b) =>
      (({ critical: 0, high: 1, medium: 2 })[a.severity] ?? 3) -
        ({ critical: 0, high: 1, medium: 2 }[b.severity] ?? 3) ||
      String(b.detected_at).localeCompare(String(a.detected_at)),
  ),
);
const allTasks = computed(() =>
  projects.value.flatMap((project) =>
    leafTasks(taskHierarchy(taskLists.value[project.project_id] || [])).map((task) => ({
      ...task,
      project_name: project.name,
    })),
  ),
);
const scopedTasks = computed(() =>
  auth.manager
    ? allTasks.value
    : allTasks.value.filter((task) =>
        task.assignments?.some((a) => a.user_id === auth.user.user_id),
      ),
);
const activeTasks = computed(() =>
  scopedTasks.value.filter(
    (task) => !["done", "cancelled"].includes(task.status),
  ),
);
const ownTasks = computed(() =>
  activeTasks.value.filter((task) =>
    task.assignments?.some((a) => a.user_id === auth.user.user_id),
  ),
);
const overdueTasks = computed(() =>
  activeTasks.value.filter(
    (task) => task.due_date && task.due_date < analysisDate.value,
  ),
);
const completedTasks = computed(() =>
  scopedTasks.value.filter((task) => task.status === "done"),
);
const projectRows = computed(() =>
  projects.value.map((project) =>
    projectOverview(
      project,
      taskLists.value[project.project_id],
      activeRisks.value.filter(
        (risk) => risk.project_id === project.project_id,
      ),
    ),
  ),
);
const featuredProjects = computed(() =>
  [...projectRows.value]
    .sort(
      (a, b) =>
        Number(b.status === "active") - Number(a.status === "active") ||
        String(a.end_date).localeCompare(String(b.end_date)),
    )
    .slice(0, 4),
);
const people = computed(() => projectTeam(projects.value));
const taskDistribution = computed(() =>
  taskGroups.map((group) => ({
    ...group,
    value: scopedTasks.value.filter((task) =>
      group.statuses.includes(task.status),
    ).length,
  })),
);
const week = computed(() =>
  weekDates(selectedDate.value || analysisDate.value),
);
const weekLabel = computed(
  () =>
    `${date(week.value[0]).slice(0, 5)} по ${date(week.value[6]).slice(0, 5)}`,
);
const weekDeadlines = computed(() =>
  activeTasks.value.filter(
    (task) => task.due_date >= week.value[0] && task.due_date <= week.value[6],
  ),
);
const dayDeadlines = computed(() =>
  weekDeadlines.value.filter((task) => task.due_date === selectedDate.value),
);
const nextDeadline = computed(
  () =>
    [...activeTasks.value]
      .filter((task) => task.due_date >= analysisDate.value)
      .sort((a, b) => a.due_date.localeCompare(b.due_date))[0],
);
const summaryText = computed(() =>
  auth.manager
    ? "Сроки, трудозатраты и риски доступных проектов"
    : "Назначенные задачи, ближайшие сроки и учёт времени",
);
function showTasks(title, items, description = "") {
  dialog.value = { kind: "tasks", title, items, description };
}
function showRisks(title, items) {
  dialog.value = { kind: "risks", title, items };
}
function showProjectList(items = projectRows.value) {
  dialog.value = { kind: "projects", title: "Доступные проекты", items };
}
function showTask(task) {
  dialog.value = { kind: "task", title: task.name, task };
}
function showPerson(person) {
  dialog.value = { kind: "person", title: person.full_name, person };
}
function selectTaskGroup(group) {
  showTasks(
    group.label,
    scopedTasks.value.filter((task) => group.statuses.includes(task.status)),
    auth.manager
      ? "Задачи и контрольные точки доступных проектов"
      : "Назначенные вам задачи и контрольные точки",
  );
}
function changeWeek(direction) {
  selectedDate.value = shiftDate(
    selectedDate.value || analysisDate.value,
    direction * 7,
  );
}
function dueLabel(task) {
  return task.due_date < analysisDate.value
    ? `Срок прошёл ${date(task.due_date)}`
    : `До ${date(task.due_date)}`;
}
function personLabel(count) {
  const last = count % 10,
    hundred = count % 100;
  return hundred >= 11 && hundred <= 14
    ? "проектов"
    : last === 1
      ? "проект"
      : last >= 2 && last <= 4
        ? "проекта"
        : "проектов";
}
</script>
<template>
  <div class="dashboard">
    <header class="dash-heading">
      <div>
        <h1>{{ pageTitle }}</h1>
        <p class="dash-subtitle">{{ summaryText }}</p>
      </div>
      <div class="heading-actions">
        <span class="date-pill"
          ><UiIcon name="calendar" />{{ dateLabel }}</span
        ><button
          class="refresh-control"
          @click="load"
          :disabled="busy"
          aria-label="Обновить рабочую панель"
        >
          <UiIcon name="refresh" />
        </button>
      </div>
    </header>
    <section v-if="loadError" class="dash-message error" role="alert">
      <UiIcon name="shield" />
      <div>
        <strong>Не удалось загрузить данные</strong>
        <p>{{ loadError }}</p>
      </div>
      <button @click="load">Повторить</button>
    </section>
    <div v-else-if="busy" class="dash-loading" role="status">
      <div class="loading-orbit" />
      <p>Собираем ваши проекты и задачи…</p>
    </div>
    <template v-else>
      <section v-if="incomplete.length" class="dash-message" role="status">
        <UiIcon name="shield" />
        <div>
          <strong>Часть задач пока недоступна</strong>
          <p>
            Не удалось загрузить {{ incomplete.length }}
            {{ personLabel(incomplete.length) }}. Показатели задач учитывают
            только загруженные данные.
          </p>
        </div>
        <button @click="load">Повторить</button>
      </section>
      <section class="dash-shortcuts" aria-label="Быстрые действия">
        <div class="shortcuts-title">
          <div>
            <h2>Продолжить работу</h2>
          </div>
        </div>
        <RouterLink to="/timebook"
          ><UiIcon name="clock" /><span>Внести время</span
          ><UiIcon name="arrow" /></RouterLink
        ><RouterLink to="/projects"
          ><UiIcon name="folder" /><span>{{
            auth.manager ? "Управлять проектами" : "Открыть проекты"
          }}</span
          ><UiIcon name="arrow" /></RouterLink
        ><RouterLink v-if="auth.manager" to="/reports/summary"
          ><UiIcon name="chart" /><span>Открыть отчёты</span
          ><UiIcon name="arrow" /></RouterLink
        ><RouterLink v-else to="/risks"
          ><UiIcon name="shield" /><span>Посмотреть риски</span
          ><UiIcon name="arrow"
        /></RouterLink>
      </section>
      <div class="dash-kpis">
        <button
          class="kpi-card"
          @click="
            showProjectList(projectRows.filter((p) => p.status === 'active'))
          "
        >
          <span class="kpi-body"
            ><span class="kpi-label">Активные проекты</span
            ><strong>{{
              number(projects.filter((p) => p.status === "active").length, 0)
            }}</strong
            ><small>из {{ projects.length }} доступных</small></span>
        </button>
        <button
          class="kpi-card"
          @click="showTasks('Завершённые задачи', completedTasks)"
        >
          <span class="kpi-body"
            ><span class="kpi-label">Завершённые задачи</span
            ><strong>{{ number(completedTasks.length, 0) }}</strong></span>
        </button>
        <button
          class="kpi-card"
          @click="showRisks('Открытые риски', priorityRisks)"
        >
          <span class="kpi-body"
            ><span class="kpi-label">Открытые риски</span
            ><strong>{{ number(activeRisks.length, 0) }}</strong
            ><small
              ><span v-if="unviewedRisks.length" class="kpi-alert"
                >{{ unviewedRisks.length }} не просмотрено</span
              ><span v-else>все просмотрены</span></small
            ></span>
        </button>
        <RouterLink
          :to="data.missing_time_warning ? { path: '/timebook', query: { from: data.previous_week.from, to: data.previous_week.to } } : '/timebook'"
          class="kpi-card"
          :class="{ 'missing-hours-card': data.missing_time_warning }"
          ><span class="kpi-body"
            ><span class="kpi-label">Мои часы за неделю</span
            ><strong
              >{{ number(data.hours_week ?? 0)
              }}<span class="value-unit">ч</span></strong
            ><small v-if="data.missing_time_warning" class="missing-hours-message">Трудозатраты за прошлую неделю не внесены</small></span></RouterLink>
      </div>
      <div class="dash-main-grid">
        <section class="dash-panel projects-panel">
          <header class="panel-heading">
            <div>
              <h2>Прогресс проектов</h2>
            </div>
            <button class="text-action" @click="showProjectList()">
              Все проекты<UiIcon name="arrow" />
            </button>
          </header>
          <div class="project-progress-list">
            <RouterLink
              v-for="p in featuredProjects"
              :key="p.project_id"
              :to="'/projects/' + p.project_id"
              class="project-progress-row"
              ><span class="project-progress-body"
                ><span class="project-line"
                  ><strong>{{ p.name }}</strong
                  ><span class="project-percent">{{
                    !p.available
                      ? "Нет данных"
                      : p.progress === null
                        ? "Нет плана"
                        : p.progress + "%"
                  }}</span></span
                ><span class="project-progress-track"
                  ><span :style="{ width: (p.progress ?? 0) + '%' }" /></span
                ><span class="project-meta"
                  ><span>{{
                    p.available
                      ? `${p.completedCount} из ${p.taskCount} задач выполнено`
                      : "Данные задач недоступны"
                  }}</span
                  ><span v-if="p.openRiskCount" class="project-risk-count" :aria-label="`Открытых рисков ${p.openRiskCount}`"
                    ><UiIcon name="shield" />{{ p.openRiskCount }}</span
                  ></span
                ></span
              ></RouterLink
            >
            <p v-if="!featuredProjects.length" class="dash-empty">
              Пока нет доступных проектов
            </p>
          </div>
        </section>
        <section class="dash-panel tasks-panel">
          <header class="panel-heading">
            <div>
              <h2>Задачи по статусам</h2>
            </div>
            <button
              class="icon-action"
              aria-label="Показать все задачи"
              @click="
                showTasks(
                  auth.manager ? 'Все задачи' : 'Мои задачи',
                  scopedTasks,
                )
              "
            >
              <UiIcon name="arrow" />
            </button>
          </header>
          <div class="task-status-list" aria-label="Распределение задач по статусам">
            <button
              v-for="group in taskDistribution"
              :key="group.key"
              class="task-status-row"
              :style="{ '--status-color': group.color }"
              @click="selectTaskGroup(group)"
            >
              <span class="task-status-label">{{ group.label }}</span>
              <strong>{{ number(group.value, 0) }}</strong>
              <small>{{ scopedTasks.length ? number(group.value / scopedTasks.length * 100, 0) : 0 }}%</small>
              <span class="task-status-track" aria-hidden="true">
                <span :style="{ width: (scopedTasks.length ? group.value / scopedTasks.length * 100 : 0) + '%' }" />
              </span>
            </button>
          </div>
          <p class="panel-note">{{ scopedTasks.length ? `Всего ${number(scopedTasks.length, 0)} задач и вех` : 'Задачи пока не добавлены' }}</p>
        </section>
        <section class="dash-panel week-panel">
          <header class="panel-heading">
            <div>
              <h2>Сроки недели</h2>
            </div>
            <button
              class="icon-action"
              @click="selectedDate = analysisDate"
              aria-label="Вернуться к текущей неделе"
            >
              <UiIcon name="calendar" />
            </button>
          </header>
          <div class="week-navigation">
            <button @click="changeWeek(-1)" aria-label="Предыдущая неделя">
              <UiIcon name="left" /></button
            ><span>{{ weekLabel }}</span
            ><button @click="changeWeek(1)" aria-label="Следующая неделя">
              <UiIcon name="right" />
            </button>
          </div>
          <div class="dash-week">
            <button
              v-for="(day, index) in week"
              :key="day"
              :class="{
                selected: day === selectedDate,
                today: day === analysisDate,
              }"
              :aria-pressed="day === selectedDate"
              :aria-label="`${date(day)}, задач со сроком ${weekDeadlines.filter((t) => t.due_date === day).length}`"
              @click="selectedDate = day"
            >
              <small>{{
                ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][index]
              }}</small
              ><strong>{{ Number(day.slice(8)) }}</strong
              ><span
                class="deadline-dot"
                :class="{
                  filled: weekDeadlines.some((t) => t.due_date === day),
                }"
              />
            </button>
          </div>
          <div class="day-deadlines">
            <p class="day-label">{{ date(selectedDate) }}</p>
            <button
              v-for="t in dayDeadlines.slice(0, 3)"
              :key="t.task_id"
              class="deadline-row"
              @click="showTask(t)"
            >
              <span
                class="deadline-bullet"
                :class="{ overdue: t.due_date < analysisDate }"
              /><span
                ><strong :class="{ 'milestone-label': t.is_milestone }">{{ t.is_milestone ? '◆ ' : '' }}{{ t.name }}</strong
                ><small>{{ t.project_name }}</small></span
              ><UiIcon name="right" />
            </button>
            <div v-if="!dayDeadlines.length" class="day-empty">
              <UiIcon name="check" /><span>На этот день сроков нет</span
              ><button
                v-if="nextDeadline && nextDeadline.due_date !== selectedDate"
                class="text-action"
                @click="selectedDate = nextDeadline.due_date"
              >
                Ближайший срок {{ date(nextDeadline.due_date).slice(0, 5)
                }}<UiIcon name="arrow" />
              </button>
            </div>
            <button
              v-if="dayDeadlines.length > 3"
              class="text-action"
              @click="showTasks('Сроки на ' + date(selectedDate), dayDeadlines)"
            >
              Ещё {{ dayDeadlines.length - 3 }}<UiIcon name="arrow" />
            </button>
          </div>
          <button
            v-if="overdueTasks.length"
            class="overdue-summary"
            @click="showTasks('Задачи с прошедшим сроком', overdueTasks)"
          >
            <UiIcon name="clock" /><span
              >Срок прошёл у {{ overdueTasks.length }} задач</span
            ><UiIcon name="arrow" />
          </button>
        </section>
        <section class="dash-panel attention-panel">
          <header class="panel-heading">
            <div>
              <h2>Требуют внимания</h2>
            </div>
            <RouterLink to="/risks" class="text-action"
              >Реестр рисков<UiIcon name="arrow"
            /></RouterLink>
          </header>
          <div v-if="data.missing_time_warning" class="time-warning">
            <span class="warning-symbol"><UiIcon name="clock" /></span>
            <div>
              <strong>Пора заполнить табель</strong>
              <p>Нет списаний с {{ date(data.previous_week.from) }} по {{ date(data.previous_week.to) }}</p>
            </div>
            <RouterLink :to="{ path: '/timebook', query: { from: data.previous_week.from, to: data.previous_week.to } }"
              >Заполнить<UiIcon name="arrow"
            /></RouterLink>
          </div>
          <RouterLink
            v-for="risk in priorityRisks.slice(0, 4)"
            :key="risk.risk_id"
            :to="'/risks/' + risk.risk_id"
            class="attention-row"
            ><span class="risk-symbol" :class="risk.severity" aria-hidden="true"></span
            ><span class="attention-copy"
              ><strong>{{ risk.type_name }}</strong
              ><small>{{
                risk.project_name || risk.subject_name || "Загрузка сотрудника"
              }}</small></span
            ><span class="risk-severity" :class="risk.severity">{{
              severities[risk.severity]
            }}</span
            ><UiIcon class="row-arrow" name="right"
          /></RouterLink>
          <div v-if="!priorityRisks.length" class="dash-empty success">
            <UiIcon name="check" /><strong>Открытых рисков нет</strong>

            <RouterLink to="/risks" class="text-action"
              >Открыть реестр<UiIcon name="arrow"
            /></RouterLink>
          </div>
        </section>
        <section v-if="auth.manager" class="dash-panel team-panel">
          <header class="panel-heading">
            <div>
              <h2>
                Команда проектов
                <span class="heading-count">{{ people.length }}</span>
              </h2>
            </div>
            <button
              class="text-action"
              @click="
                dialog = {
                  kind: 'people',
                  title: 'Команда проектов',
                  items: people,
                }
              "
            >
              Все<UiIcon name="arrow" />
            </button>
          </header>
          <div class="team-list">
            <button
              v-for="person in people.slice(0, 5)"
              :key="person.user_id"
              class="team-row"
              @click="showPerson(person)"
            >
              <span class="person-avatar">{{
                initials(person.full_name)
              }}</span
              ><span class="team-person"
                ><strong>{{ person.full_name }}</strong
                ><small>{{
                  person.job_title || "Участник проекта"
                }}</small></span
              ><span class="person-projects"
                >{{ person.projects.length }}
                {{ personLabel(person.projects.length) }}</span
              ><UiIcon class="row-arrow" name="right" />
            </button>
          </div>
          <p v-if="!people.length" class="dash-empty">
            Участники появятся после добавления в проект
          </p>
        </section>
        <section v-else class="dash-panel team-panel">
          <header class="panel-heading">
            <div>
              <h2>
                Мои задачи
                <span class="heading-count">{{ ownTasks.length }}</span>
              </h2>
            </div>
            <button
              class="text-action"
              @click="showTasks('Мои задачи', ownTasks)"
            >
              Все<UiIcon name="arrow" />
            </button>
          </header>
          <button
            v-for="t in [...ownTasks]
              .sort((a, b) =>
                String(a.due_date).localeCompare(String(b.due_date)),
              )
              .slice(0, 4)"
            :key="t.task_id"
            class="my-task-row"
            @click="showTask(t)"
          >
            <span class="task-check"><UiIcon name="tasks" /></span
            ><span
              ><strong :class="{ 'milestone-label': t.is_milestone }">{{ t.is_milestone ? '◆ ' : '' }}{{ t.name }}</strong
              ><small>{{ dueLabel(t) }}</small></span
            ><span class="my-task-progress">{{ taskProgress(t) }}%</span
            ><UiIcon class="row-arrow" name="right" />
          </button>
          <p v-if="!ownTasks.length" class="dash-empty">
            Все назначенные задачи выполнены или новых назначений пока нет
          </p>
        </section>
      </div>
    </template>
    <Modal v-if="dialog" :title="dialog.title" @close="dialog = null"
      ><div class="dash-detail">
        <template v-if="dialog.kind === 'projects'"
          ><RouterLink
            v-for="p in dialog.items"
            :key="p.project_id"
            :to="'/projects/' + p.project_id"
            class="detail-row"
            @click="dialog = null"
            ><span class="detail-symbol"><UiIcon name="folder" /></span
            ><span
              ><strong>{{ p.name }}</strong
              ><small
                >{{ projectStatuses[p.status] }} · до
                {{ date(p.end_date) }}</small
              ></span
            ><span v-if="p.progress !== null" class="detail-value"
              >{{ p.progress }}%</span
            ><UiIcon name="arrow"
          /></RouterLink>
          <p v-if="!dialog.items.length" class="dash-empty">
            Проектов с таким состоянием пока нет
          </p></template
        >
        <template v-if="dialog.kind === 'tasks'"
          ><button
            v-for="t in dialog.items"
            :key="t.task_id"
            class="detail-row"
            @click="showTask(t)"
          >
            <span class="detail-symbol"
              ><UiIcon
                :name="t.is_milestone ? 'calendar' : 'tasks'" /></span
            ><span
              ><strong :class="{ 'milestone-label': t.is_milestone }">{{ t.is_milestone ? '◆ ' : '' }}{{ t.name }}</strong
              ><small
                >{{ t.project_name }} · {{ taskStatuses[t.status] }}</small
              ></span
            ><span class="detail-date">{{ date(t.due_date) }}</span
            ><UiIcon name="right" />
          </button>
          <p v-if="!dialog.items.length" class="dash-empty">
            Задач с таким состоянием нет
          </p></template
        >
        <template v-if="dialog.kind === 'risks'"
          ><RouterLink
            v-for="risk in dialog.items"
            :key="risk.risk_id"
            :to="'/risks/' + risk.risk_id"
            class="detail-row"
            @click="dialog = null"
            ><span class="risk-symbol" :class="risk.severity" aria-hidden="true"></span
            ><span
              ><strong>{{ risk.type_name }}</strong
              ><small>{{ risk.project_name || risk.subject_name }}</small></span
            ><span class="risk-severity" :class="risk.severity">{{
              severities[risk.severity]
            }}</span
            ><UiIcon name="arrow"
          /></RouterLink>
          <p v-if="!dialog.items.length" class="dash-empty">
            Открытых рисков нет
          </p></template
        >
        <template v-if="dialog.kind === 'people'"
          ><button
            v-for="person in dialog.items"
            :key="person.user_id"
            class="detail-row"
            @click="showPerson(person)"
          >
            <span class="person-avatar">{{ initials(person.full_name) }}</span
            ><span
              ><strong>{{ person.full_name }}</strong
              ><small>{{ person.job_title || "Участник проекта" }}</small></span
            ><span class="person-projects"
              >{{ person.projects.length }}
              {{ personLabel(person.projects.length) }}</span
            ><UiIcon name="right" />
          </button>
          <p v-if="!dialog.items.length" class="dash-empty">
            В доступных проектах пока нет участников
          </p></template
        >
        <template v-if="dialog.kind === 'person'"
          ><div class="person-detail-head">
            <span class="person-avatar large">{{
              initials(dialog.person.full_name)
            }}</span>
            <div>
              <strong>{{ dialog.person.full_name }}</strong>
              <p>{{ dialog.person.job_title || "Участник проекта" }}</p>
            </div>
          </div>
          <h3>Участие в доступных вам проектах</h3>
          <RouterLink
            v-for="p in dialog.person.projects"
            :key="p.project_id"
            :to="'/projects/' + p.project_id"
            class="detail-row"
            @click="dialog = null"
            ><span class="detail-symbol"><UiIcon name="folder" /></span
            ><strong>{{ p.name }}</strong
            ><UiIcon name="arrow" /></RouterLink
        ></template>
        <template v-if="dialog.kind === 'task'"
          ><span class="task-status-pill">{{
            taskStatuses[dialog.task.status]
          }}</span>
          <p class="task-detail-description">
            {{ dialog.task.description || "Описание задачи пока не добавлено" }}
          </p>
          <dl class="task-detail-facts">
            <div>
              <dt>Проект</dt>
              <dd>{{ dialog.task.project_name }}</dd>
            </div>
            <div>
              <dt>Плановый срок</dt>
              <dd>{{ date(dialog.task.due_date) }}</dd>
            </div>
            <div>
              <dt>Готовность</dt>
              <dd>{{ taskProgress(dialog.task) }}%</dd>
            </div>
            <div>
              <dt>Плановые трудозатраты</dt>
              <dd>{{ number(dialog.task.planned_hours) }} ч</dd>
            </div>
            <div>
              <dt>Исполнители</dt>
              <dd>
                {{
                  dialog.task.assignments?.map((p) => p.full_name).join(", ") ||
                  "Не назначены"
                }}
              </dd>
            </div>
          </dl>
          <RouterLink
            :to="'/projects/' + dialog.task.project_id"
            class="detail-primary-action"
            @click="dialog = null"
            >Открыть проект<UiIcon name="arrow" /></RouterLink
        ></template></div
    ></Modal>
  </div>
</template>
<style scoped>
.dashboard,
.dash-detail {
  --risk-high: var(--warning);
  --risk-critical: var(--danger);
  color: var(--text);
  font-size: 14px;
  line-height: 1.5;
  font-variant-numeric: tabular-nums;
}
.dashboard {
  display: grid;
  gap: 24px;
  min-width: 0;
}
.dashboard :deep(svg),
.dash-detail :deep(svg) {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  stroke-width: 1.5;
}
.dash-heading,
.heading-actions,
.panel-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.dash-heading h1 {
  margin: 0;
  font-size: 32px;
  line-height: 40px;
  font-weight: 500;
  letter-spacing: 0;
}
.dash-subtitle {
  color: var(--secondary);
  font-size: 14px;
  line-height: 20px;
  margin: 8px 0 0;
}
.heading-actions {
  justify-content: flex-end;
  gap: 12px;
  flex-shrink: 0;
}
.date-pill {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--secondary);
  font-size: 13px;
  white-space: nowrap;
}
.refresh-control,
.icon-action,
.week-navigation button {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  min-height: 36px;
  padding: 0;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: var(--secondary);
}
.refresh-control {
  background: var(--card);
  border-color: var(--border);
}
.refresh-control:hover,
.icon-action:hover,
.week-navigation button:hover {
  background: var(--inset);
  color: var(--text);
}
.dash-shortcuts {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.shortcuts-title {
  margin-right: auto;
}
.shortcuts-title h2 {
  font-size: 13px;
  font-weight: 400;
  color: var(--secondary);
  line-height: 20px;
  margin: 0 16px 0 0;
}
.dash-shortcuts > a {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 40px;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--card);
  color: var(--text);
  font-size: 13px;
  font-weight: 500;
}
.dash-shortcuts > a:hover {
  text-decoration: none;
  background: var(--inset);
}
.dash-shortcuts > a svg {
  color: var(--secondary);
}
.dash-kpis {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}
.kpi-card {
  display: flex;
  align-items: flex-start;
  min-width: 0;
  padding: 20px;
  text-align: left;
  color: var(--text);
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  transition: background-color 160ms cubic-bezier(0.22, 1, 0.36, 1), border-color 160ms cubic-bezier(0.22, 1, 0.36, 1);
}
.kpi-card:hover {
  background: var(--inset);
  border-color: color-mix(in srgb, var(--text) 20%, var(--border));
  text-decoration: none;
}
.kpi-body {
  display: grid;
  grid-template-rows: minmax(20px, auto) 40px minmax(16px, auto);
  align-content: start;
  gap: 8px;
  min-width: 0;
}
.kpi-label {
  color: var(--secondary);
  font-size: 13px;
  line-height: 20px;
  font-weight: 400;
}
.kpi-body strong {
  font-size: 32px;
  line-height: 40px;
  font-weight: 500;
  letter-spacing: 0;
}
.kpi-body small {
  color: var(--muted);
  font-size: 12px;
  line-height: 16px;
  font-weight: 400;
}
.kpi-card.missing-hours-card {
  border-color: var(--warning);
  background: color-mix(in srgb, var(--warning) 7%, var(--card));
}
.dashboard .milestone-label,
.dash-detail .milestone-label { color: var(--milestone); }
.missing-hours-card .kpi-body .missing-hours-message {
  color: var(--warning);
  font-weight: 600;
  line-height: 1.45;
}
.value-unit {
  margin-left: 8px;
  font-size: 14px;
  font-weight: 400;
  color: var(--secondary);
}
.kpi-alert {
  color: var(--risk-high);
}
.dash-main-grid {
  display: grid;
  grid-template-columns: repeat(12, minmax(0, 1fr));
  gap: 24px;
  align-items: stretch;
}
.dash-panel {
  display: flex;
  flex-direction: column;
  min-width: 0;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 24px;
}
.projects-panel {
  grid-column: span 8;
}
.tasks-panel {
  grid-column: span 4;
}
.week-panel {
  grid-column: span 4;
}
.attention-panel {
  grid-column: span 8;
}
.team-panel {
  grid-column: span 12;
}
.panel-heading {
  min-height: 36px;
  margin-bottom: 16px;
  gap: 12px;
}
.panel-heading > div {
  min-width: 0;
}
.panel-heading h2 {
  font-size: 16px;
  line-height: 24px;
  font-weight: 500;
  letter-spacing: 0;
  margin: 0;
}
.text-action {
  display: inline-flex;
  align-items: center;
  justify-content: flex-start;
  gap: 8px;
  padding: 4px;
  min-height: 32px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--secondary);
  font-size: 13px;
  font-weight: 400;
  text-align: left;
}
.text-action:hover {
  color: var(--text);
  background: var(--inset);
  text-decoration: none;
}
.project-progress-list {
  display: grid;
  align-content: start;
  gap: 8px;
  flex: 1;
}
.project-progress-row {
  display: block;
  min-width: 0;
  padding: 12px 8px;
  color: var(--text);
  border-radius: 8px;
}
.project-progress-row:hover {
  background: var(--inset);
  text-decoration: none;
}
.project-progress-body {
  display: block;
  min-width: 0;
}
.project-line {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 12px;
}
.project-line strong {
  flex: 1;
  min-width: 0;
  font-size: 14px;
  line-height: 20px;
  font-weight: 500;
  overflow-wrap: anywhere;
}
.project-percent {
  min-width: 48px;
  text-align: right;
  font-size: 14px;
  line-height: 20px;
  font-weight: 500;
  white-space: nowrap;
}
.project-progress-track,
.task-status-track {
  display: block;
  height: 4px;
  border-radius: 2px;
  overflow: hidden;
  background: var(--inset);
}
.project-progress-track > span,
.task-status-track > span {
  display: block;
  height: 100%;
  max-width: 100%;
  border-radius: inherit;
  background: var(--accent);
}
.project-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 8px;
  font-size: 12px;
  line-height: 16px;
  color: var(--muted);
}
.project-risk-count {
  display: flex;
  align-items: center;
  gap: 4px;
  color: var(--risk-high);
}
.task-status-list {
  display: grid;
  gap: 8px;
}
.task-status-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 36px 40px;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-width: 0;
  border: 0;
  border-radius: 8px;
  background: transparent;
  padding: 12px 8px;
  font-size: 13px;
  line-height: 20px;
  text-align: left;
}
.task-status-row:hover {
  background: var(--inset);
}
.task-status-label {
  color: var(--secondary);
  font-weight: 400;
}
.task-status-row strong,
.task-status-row small {
  text-align: right;
  font-size: 13px;
  font-weight: 500;
}
.task-status-row small {
  color: var(--muted);
  font-size: 12px;
  font-weight: 400;
}
.task-status-track {
  grid-column: 1 / -1;
}
.task-status-track > span {
  background: var(--status-color);
}
.panel-note {
  margin: auto 8px 0;
  padding-top: 16px;
  color: var(--muted);
  font-size: 12px;
  line-height: 16px;
}
.week-navigation {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 13px;
  color: var(--secondary);
}
.dash-week {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 4px;
  border-bottom: 1px solid var(--border);
  padding-bottom: 16px;
}
.dash-week button {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  min-width: 0;
  border: 0;
  border-radius: 8px;
  padding: 8px 0;
  background: transparent;
  color: var(--text);
}
.dash-week button:hover {
  background: var(--inset);
}
.dash-week small {
  color: var(--muted);
  font-size: 12px;
  line-height: 16px;
  font-weight: 400;
}
.dash-week strong {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  font-size: 14px;
  font-weight: 500;
  border: 1px solid transparent;
  border-radius: 4px;
}
.dash-week .today strong {
  border-color: var(--accent);
}
.dash-week .selected strong {
  color: var(--card);
  background: var(--text);
}
.deadline-dot {
  width: 4px;
  height: 4px;
  border-radius: 50%;
}
.deadline-dot.filled {
  background: var(--accent);
}
.day-deadlines {
  flex: 1;
  padding-top: 16px;
  min-height: 128px;
}
.day-label {
  margin: 0 0 8px;
  font-size: 12px;
  color: var(--muted);
}
.deadline-row,
.attention-row,
.team-row,
.my-task-row,
.detail-row {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  min-width: 0;
  padding: 12px 8px;
  text-align: left;
  background: transparent;
  color: var(--text);
  border: 0;
  border-radius: 8px;
}
.deadline-row:hover,
.attention-row:hover,
.team-row:hover,
.my-task-row:hover,
.detail-row:hover {
  background: var(--inset);
  text-decoration: none;
}
.deadline-row > span:nth-child(2),
.attention-copy,
.team-person,
.my-task-row > span:nth-child(2),
.detail-row > span:nth-child(2),
.detail-row > strong {
  flex: 1;
  min-width: 0;
}
.deadline-row strong,
.attention-copy strong,
.team-person strong,
.my-task-row strong,
.detail-row strong {
  display: block;
  font-size: 14px;
  line-height: 20px;
  font-weight: 500;
  overflow-wrap: anywhere;
}
.deadline-row small,
.attention-copy small,
.team-person small,
.my-task-row small,
.detail-row small {
  display: block;
  margin-top: 4px;
  color: var(--muted);
  font-size: 12px;
  line-height: 16px;
}
.deadline-row > svg,
.row-arrow,
.detail-row > svg {
  color: var(--muted);
}
.deadline-bullet {
  width: 4px;
  height: 24px;
  flex-shrink: 0;
  border-radius: 2px;
  background: var(--border);
}
.deadline-bullet.overdue {
  background: var(--risk-high);
}
.day-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 8px;
  min-height: 112px;
  color: var(--muted);
  font-size: 13px;
  text-align: center;
}
.day-empty > svg {
  color: var(--muted);
}
.overdue-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 40px;
  padding: 8px 12px;
  margin-top: 16px;
  text-align: left;
  border: 0;
  border-radius: 8px;
  color: var(--risk-high);
  background: color-mix(in srgb, var(--risk-high) 7%, var(--card));
  font-size: 13px;
  font-weight: 400;
}
.overdue-summary span {
  flex: 1;
}
.overdue-summary:hover {
  background: color-mix(in srgb, var(--risk-high) 12%, var(--card));
}
.attention-row + .attention-row,
.my-task-row + .my-task-row,
.detail-row + .detail-row {
  border-top: 1px solid var(--border);
}
.risk-symbol {
  --risk-tone: var(--risk-medium);
  display: block;
  height: 32px;
  width: 4px;
  flex-shrink: 0;
  background: var(--risk-tone);
  border-radius: 2px;
}
.risk-symbol.high,
.risk-severity.high {
  --risk-tone: var(--risk-high);
}
.risk-symbol.critical,
.risk-severity.critical {
  --risk-tone: var(--risk-critical);
}
.risk-severity {
  --risk-tone: var(--risk-medium);
  color: var(--risk-tone);
  font-size: 12px;
  font-weight: 400;
  white-space: nowrap;
}
.time-warning {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  margin-bottom: 8px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--risk-high) 7%, var(--card));
}
.time-warning > div {
  flex: 1;
  min-width: 0;
}
.time-warning strong {
  font-size: 14px;
  font-weight: 500;
}
.time-warning p {
  margin: 4px 0 0;
  color: var(--secondary);
  font-size: 12px;
}
.time-warning > a {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--risk-high);
  font-size: 13px;
}
.warning-symbol {
  color: var(--risk-high);
}
.heading-count {
  margin-left: 8px;
  color: var(--muted);
  font-size: 13px;
  font-weight: 400;
}
.team-list {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px 24px;
}
.person-avatar,
.task-check,
.detail-symbol {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  color: var(--secondary);
  background: var(--inset);
}
.person-avatar {
  font-size: 12px;
  font-weight: 500;
}
.person-projects,
.my-task-progress,
.detail-date,
.detail-value {
  color: var(--secondary);
  font-size: 12px;
  white-space: nowrap;
  font-weight: 400;
}
.team-list .person-projects,
.team-list .row-arrow {
  display: none;
}
.dash-message {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px;
  border: 1px solid var(--border);
  border-left: 4px solid var(--risk-high);
  border-radius: 12px;
  color: var(--text);
  background: var(--card);
}
.dash-message > div {
  flex: 1;
  min-width: 0;
}
.dash-message > svg {
  color: var(--risk-high);
}
.dash-message p {
  margin: 4px 0 0;
  color: var(--secondary);
  font-size: 13px;
}
.dash-message.error {
  border-left-color: var(--danger);
}
.dash-message.error > svg {
  color: var(--danger);
}
.dash-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  min-height: 320px;
  color: var(--muted);
}
.loading-orbit {
  width: 32px;
  height: 32px;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: orbit 800ms linear infinite;
}
@keyframes orbit {
  to { transform: rotate(360deg); }
}
.dash-empty {
  margin: auto 0;
  padding: 32px 16px;
  text-align: center;
  color: var(--muted);
  font-size: 13px;
}
.dash-empty.success {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 8px;
}
.person-detail-head {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 24px;
}
.person-avatar.large {
  width: 48px;
  height: 48px;
  font-size: 16px;
  border-radius: 12px;
}
.person-detail-head p {
  color: var(--secondary);
  font-size: 13px;
  margin: 4px 0 0;
}
.task-status-pill {
  display: inline-block;
  padding: 4px 8px;
  border-radius: 4px;
  color: var(--secondary);
  background: var(--inset);
  font-size: 12px;
}
.task-detail-description {
  color: var(--secondary);
  margin: 16px 0;
  white-space: pre-wrap;
}
.task-detail-facts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px 24px;
  margin: 24px 0;
}
.task-detail-facts dt {
  color: var(--muted);
  margin-bottom: 4px;
  font-size: 12px;
}
.task-detail-facts dd {
  margin: 0;
  font-size: 14px;
  overflow-wrap: anywhere;
}
.detail-primary-action {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 40px;
  padding: 8px 16px;
  border-radius: 8px;
  background: var(--text);
  color: var(--card);
  font-size: 14px;
  font-weight: 500;
}
.detail-primary-action:hover {
  background: var(--secondary);
  text-decoration: none;
}
@media (max-width: 1200px) {
  .dash-main-grid {
    gap: 16px;
  }
  .dash-panel {
    padding: 20px;
  }
  .projects-panel,
  .attention-panel {
    grid-column: span 7;
  }
  .tasks-panel,
  .week-panel {
    grid-column: span 5;
  }
  .team-list {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .shortcuts-title {
    flex-basis: 100%;
    margin-bottom: 4px;
  }
  .dash-heading {
    align-items: flex-start;
  }
  .heading-actions {
    gap: 8px;
  }
}
@media (max-width: 1000px) {
  .dash-kpis {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .kpi-body {
    grid-template-rows: minmax(20px, auto) 40px minmax(16px, auto);
  }
  .dash-heading {
    flex-wrap: wrap;
  }
  .heading-actions {
    justify-content: flex-start;
  }
}
@media (max-width: 760px) {
  .dashboard {
    gap: 20px;
  }
  .dash-heading h1 {
    font-size: 28px;
    line-height: 36px;
  }
  .dash-main-grid {
    grid-template-columns: minmax(0, 1fr);
  }
  .projects-panel,
  .tasks-panel,
  .week-panel,
  .attention-panel,
  .team-panel {
    grid-column: 1;
  }
  .dash-panel {
    padding: 16px;
    border-radius: 12px;
  }
  .kpi-card {
    padding: 16px;
  }
  .dash-shortcuts > a {
    flex: 1 1 100%;
    min-height: 44px;
  }
  .dash-shortcuts > a svg:last-child {
    margin-left: auto;
  }
  .team-list {
    grid-template-columns: 1fr;
  }
  .team-list .person-projects {
    display: block;
  }
  .panel-heading {
    flex-wrap: wrap;
    gap: 8px;
  }
  .risk-severity {
    white-space: normal;
    text-align: right;
    max-width: 80px;
  }
  .attention-row,
  .detail-row {
    gap: 8px;
  }
  .attention-row .row-arrow {
    display: none;
  }
  .time-warning {
    flex-wrap: wrap;
  }
  .time-warning > a {
    margin-left: auto;
  }
  .task-detail-facts {
    grid-template-columns: 1fr;
  }
  .detail-row .detail-date {
    display: none;
  }
  .dash-message {
    flex-wrap: wrap;
  }
  .dash-message button {
    margin-left: auto;
  }
}
@media (prefers-reduced-motion: reduce) {
  .kpi-card {
    transition: none;
  }
  .loading-orbit {
    animation: none;
  }
}
</style>
