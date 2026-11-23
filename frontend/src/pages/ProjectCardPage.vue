<script setup>
import { ref, computed, onMounted, watch, nextTick } from "vue";
import { useRoute, useRouter } from "vue-router";
import { api, download } from "../common/api/client.js";
import { useAuth } from "../common/stores/auth.js";
import { useUi } from "../common/stores/ui.js";
import {
  list,
  date,
  number,
  projectStatuses,
  taskStatuses,
  taskProgress,
  filterTasks,
  today,
  iso,
  planRows,
} from "../common/utils/format.js";
import Modal from "../common/components/Modal.vue";
import SearchSelect from "../common/components/SearchSelect.vue";
import TimeEntryGroups from "../modules/time-tracking/views/TimeEntryGroups.vue";
import RiskBadge from "../common/components/RiskBadge.vue";
import BarChart from "../common/components/BarChart.vue";
import GanttView from "../modules/time-tracking/views/GanttView.vue";
import KanbanBoard from "../modules/time-tracking/views/KanbanBoard.vue";
import TaskCard from "../modules/time-tracking/views/TaskCard.vue";
import ResourcePlan from "../modules/time-tracking/views/ResourcePlan.vue";
import RiskRegistry from "../modules/risks/views/RiskRegistry.vue";
import {
  filterProjectTasks,
  includeTaskAncestors,
  taskDepth,
  taskHierarchy,
  taskLabel,
} from "../modules/time-tracking/taskFilters.js";
const route = useRoute(),
  router = useRouter(),
  auth = useAuth(),
  ui = useUi(),
  id = Number(route.params.id),
  project = ref(null),
  tasks = ref([]),
  releases = ref([]),
  indicators = ref({ tasks: {}, users: {}, project: [] }),
  metrics = ref({ project: {}, members: [] }),
  users = ref([]),
  tab = ref(String(route.query.tab || "summary")),
  view = ref(String(route.query.view || "table")),
  release = ref(route.query.release || ""),
  taskSearch = ref(String(route.query.search || "")),
  assignee = ref(String(route.query.assignee || "")),
  riskOnly = ref(route.query.risk === "1"),
  boardStatuses = ref(
    String(route.query.statuses || "")
      .split(",")
      .filter(Boolean),
  ),
  selected = ref(null),
  dialog = ref(""),
  form = ref({}),
  memberId = ref(null),
  managerChangeConfirmed = ref(false),
  busy = ref(true);
const editable = computed(
  () =>
    auth.admin ||
    (auth.manager && project.value?.manager_id === auth.user.user_id),
);
const members = computed(() => [...(project.value?.members || [])].sort((a, b) => a.full_name.localeCompare(b.full_name, "ru")));
const managers = computed(() =>
  users.value.filter((u) => ["admin", "manager"].includes(u.role)).sort((a, b) => a.full_name.localeCompare(b.full_name, "ru")),
);
const changingManager = computed(
  () =>
    dialog.value === "project" &&
    form.value.manager_id !== project.value?.manager_id,
);
watch(
  () => form.value.manager_id,
  () => {
    managerChangeConfirmed.value = false;
  },
);
const matchingTasks = computed(() =>
  filterProjectTasks(filterTasks(tasks.value, release.value), {
    query: taskSearch.value,
    assignee: assignee.value,
    riskOnly: riskOnly.value,
    indicators: indicators.value.tasks,
  }).filter(
    (task) =>
      tab.value !== "board" ||
      !boardStatuses.value.length ||
      boardStatuses.value.includes(task.status),
  ),
);
const visible = computed(() =>
  tab.value === "board"
    ? matchingTasks.value.map(task => ({ ...task, wbs: taskNumber(task) }))
    : includeTaskAncestors(planRows(tasks.value), matchingTasks.value),
);
const taskAssignees = computed(() =>
  [
    ...new Map(
      [
        ...members.value,
        ...tasks.value.flatMap((task) => task.assignments || []),
      ].map((person) => [person.user_id, person]),
    ).values(),
  ].sort((a, b) => a.full_name.localeCompare(b.full_name, "ru")),
);
const hasTaskFilters = computed(() =>
  Boolean(
    taskSearch.value ||
    assignee.value ||
    riskOnly.value ||
    release.value ||
    boardStatuses.value.length,
  ),
);
const taskStats = computed(() => ({
  total: matchingTasks.value.length,
  active: matchingTasks.value.filter((task) =>
    ["dev", "review", "testing", "release_wait"].includes(task.status),
  ).length,
  done: matchingTasks.value.filter((task) => task.status === "done").length,
  overdue: matchingTasks.value.filter(
    (task) =>
      task.due_date < today() && !["done", "cancelled"].includes(task.status),
  ).length,
}));
function resetTaskFilters() {
  taskSearch.value = "";
  assignee.value = "";
  riskOnly.value = false;
  release.value = "";
  boardStatuses.value = [];
}
const tabs = computed(() => [
  ["summary", "Обзор"],
  ["plan", "Календарный план"],
  ["board", "Доска задач"],
  ...(editable.value ? [["resources", "Ресурсный план"]] : []),
  ["risks", "Риски"],
  ...(editable.value ? [["labor", "Трудозатраты"]] : []),
]);
async function load() {
  const [p, t, r, i, m] = await Promise.all([
    api.get("/projects/" + id),
    api.get(`/projects/${id}/tasks`),
    api.get(`/projects/${id}/releases`),
    api.get(`/projects/${id}/risk-indicators`),
    api.get(`/projects/${id}/metrics`),
  ]);
  project.value = p.project || p;
  tasks.value = list(t).map(task => ({ ...task, assignments: [...(task.assignments || [])].sort((a,b) => a.full_name.localeCompare(b.full_name, "ru")) }));
  releases.value = list(r);
  indicators.value = i;
  metrics.value = m;
  if (tab.value === "labor" && editable.value) await loadLabor();
}
onMounted(async () => {
  await ui.act(async () => {
    await load();
    await team();
  }, "");
  busy.value = false;
  await applyLocation();
});
function canEditTask(t) {
  return (
    editable.value ||
    t.assignments?.some((a) => a.user_id === auth.user.user_id)
  );
}
async function move(t, status) {
  if (!canEditTask(t)) return;
  await ui.act(async () => {
    await api.put("/tasks/" + t.task_id, { status });
    await load();
  }, "Статус задачи обновлён");
}
function newTask(status = "backlog") {
  if (!editable.value) return;
  const initialStatus =
    typeof status === "string" && taskStatuses[status] ? status : "backlog";
  form.value = {
    name: "",
    description: "",
    start_date: project.value.start_date,
    due_date: project.value.end_date,
    status: initialStatus,
    progress_pct: initialStatus === "done" ? 100 : 0,
    is_milestone: false,
    parent_task_id: null,
    release_id: release.value ? Number(release.value) : null,
  };
  dialog.value = "task";
}
function newRelease() {
  form.value = {
    name: "",
    description: "",
    release_date: project.value.end_date,
  };
  dialog.value = "release";
}
function editProject() {
  form.value = { ...project.value };
  managerChangeConfirmed.value = false;
  dialog.value = "project";
}
async function save() {
  await ui.act(async () => {
    if (changingManager.value && !managerChangeConfirmed.value)
      throw new Error("Подтвердите смену руководителя проекта");
    if (dialog.value === "task") {
      if (form.value.is_milestone) form.value.due_date = form.value.start_date;
      await api.post(`/projects/${id}/tasks`, form.value);
    } else if (dialog.value === "release") {
      if (form.value.release_id)
        await api.put("/releases/" + form.value.release_id, form.value);
      else await api.post(`/projects/${id}/releases`, form.value);
    } else
      await api.put("/projects/" + id, {
        ...form.value,
        member_ids: members.value.map((u) => u.user_id),
      });
    dialog.value = "";
    await load();
  });
}
async function team() {
  if (editable.value)
    await ui.act(
      async () => (users.value = list(await api.get("/users/options")).sort((a, b) => a.full_name.localeCompare(b.full_name, "ru"))),
      "",
    );
}
async function addMember() {
  await ui.act(async () => {
    await api.put(`/projects/${id}/members`, {
      user_ids: [...members.value.map((u) => u.user_id), memberId.value],
    });
    memberId.value = null;
    await load();
  }, "Участник добавлен");
}
async function removeMember(u) {
  if (!window.confirm("Исключить участника из проекта?")) return;
  await ui.act(async () => {
    await api.put(`/projects/${id}/members`, {
      user_ids: members.value
        .filter((m) => m.user_id !== u.user_id)
        .map((m) => m.user_id),
    });
    await load();
  }, "Участник исключён");
}
async function dates(taskId, start, end) {
  await ui.act(async () => {
    await api.put("/tasks/" + taskId, {
      start_date: iso(start),
      due_date: iso(end),
    });
    await load();
  });
}
async function progress(taskId, progress_pct) {
  await ui.act(async () => {
    await api.put("/tasks/" + taskId, { progress_pct });
    await load();
  });
}
async function deleteRelease() {
  if (!window.confirm("Удалить релиз?")) return;
  await ui.act(async () => {
    await api.del("/releases/" + form.value.release_id);
    dialog.value = "";
    await load();
  }, "Релиз удалён");
}
async function scan() {
  await ui.act(async () => {
    await api.post("/risks/scan", { project_ids: [id] });
    await load();
  }, "Анализ рисков завершён");
}
function taskNumber(task) {
  const path = [];
  let current = task;
  const seen = new Set();
  while (current && !seen.has(current.task_id)) {
    seen.add(current.task_id);
    const siblings = tasks.value.filter(
      (x) => x.parent_task_id === current.parent_task_id,
    );
    path.unshift(siblings.indexOf(current) + 1);
    current = tasks.value.find((x) => x.task_id === current.parent_task_id);
  }
  return path.join(".");
}
function selectTab(key) {
  selected.value = null;
  tab.value = key;
}
async function applyLocation() {
  const target = String(route.query.tab || "summary");
  tab.value = tabs.value.some(([key]) => key === target) ? target : "summary";
  if (route.query.task)
    selected.value =
      tasks.value.find((t) => t.task_id === Number(route.query.task)) || null;
  await nextTick();
  if (route.query.user)
    document
      .getElementById(`resource-user-${route.query.user}`)
      ?.scrollIntoView({ block: "center", behavior: "smooth" });
}
watch(() => route.query, applyLocation);
watch(
  [tab, view, release, taskSearch, assignee, riskOnly, selected, boardStatuses],
  () => {
    if (busy.value) return;
    const query = { ...route.query, tab: tab.value, view: view.value };
    const optional = {
      release: release.value,
      search: taskSearch.value,
      assignee: assignee.value,
      risk: riskOnly.value ? "1" : "",
      task: selected.value?.task_id,
      statuses: boardStatuses.value.join(","),
    };
    for (const [key, value] of Object.entries(optional)) {
      if (value) query[key] = String(value);
      else delete query[key];
    }
    if (tab.value !== "resources") delete query.user;
    router.replace({ path: route.path, query });
  },
  { deep: true },
);
const laborEntries = ref([]), laborUser = ref(""), laborTask = ref(""), laborFrom = ref(""), laborTo = ref(""), laborBusy = ref(false);
let laborRequest = 0;
async function loadLabor() {
  const current = ++laborRequest;
  laborBusy.value = true;
  try {
    const entries = list(await api.get(`/time-entries?project_id=${id}`));
    const byTask = new Map(taskHierarchy(tasks.value).map(task => [task.task_id, task]));
    if (current === laborRequest) laborEntries.value = entries.map(entry => {
      const task = byTask.get(entry.task_id);
      return { ...entry, task_depth: task?.depth || 0, task_wbs: task?.wbs || "", task_is_milestone: Boolean(task?.is_milestone) };
    });
  } finally {
    if (current === laborRequest) laborBusy.value = false;
  }
}
watch(tab, (value) => {
  if (value === "labor" && !busy.value && editable.value) ui.act(loadLabor, "");
});
const laborPeople = computed(() => [...new Map([
  ...members.value.map(person => [person.user_id, person.full_name]),
  ...laborEntries.value.map(entry => [entry.user_id, entry.user_name]),
]).entries()].sort((a, b) => String(a[1]).localeCompare(String(b[1]), "ru")));
const filteredLabor = computed(() => laborEntries.value.filter(entry =>
  (!laborUser.value || String(entry.user_id) === String(laborUser.value)) &&
  (!laborTask.value || String(entry.task_id) === String(laborTask.value)) &&
  (!laborFrom.value || entry.work_date >= laborFrom.value) &&
  (!laborTo.value || entry.work_date <= laborTo.value),
));
const laborTotal = computed(() => filteredLabor.value.reduce((sum, entry) => sum + Number(entry.hours), 0));
const laborReportLocation = computed(() => ({path: "/reports/labor", query: {
  project: String(id), ...(laborUser.value ? {user: String(laborUser.value)} : {}),
  ...(laborFrom.value ? {from: laborFrom.value} : {}), ...(laborTo.value ? {to: laborTo.value} : {}),
}}));

const metricLabels = {
  bac: "Общий план, ч",
  pv: "План к дате, ч",
  ev: "Выполненный объём, ч",
  ac: "Фактические часы",
  eac: "Прогноз трудозатрат, ч",
  spi: "Соблюдение сроков",
  cpi: "Эффективность трудозатрат",
  s: "Прогноз сдвига, дн.",
};
</script>
<template>
  <p v-if="busy" class="loading">Загружаем проект…</p>
  <template v-else-if="project"
    ><div class="page-head">
      <div>
        <RouterLink to="/projects">← Проекты</RouterLink>
        <h1>{{ project.name }}</h1>
        <p>
          {{ date(project.start_date) }} по {{ date(project.end_date) }} ·
          {{ projectStatuses[project.status] }}
        </p>
      </div>
      <div v-if="editable" class="toolbar">
        <button @click="editProject">Изменить проект</button
        ><button class="primary" @click="scan">Повторный анализ</button>
      </div>
    </div>
    <RiskBadge :risks="indicators.project || []" />
    <nav class="tabs" aria-label="Разделы проекта">
      <button
        v-for="[key, label] in tabs"
        :key="key"
        :class="{ active: tab === key }"
        @click="selectTab(key)"
      >
        {{ label }}
      </button>
    </nav>
    <template v-if="tab === 'summary'"
      ><div class="grid stats">
        <div
          v-for="key in ['bac', 'pv', 'ev', 'ac', 'eac']"
          :key="key"
          class="stat"
        >
          <span>{{ metricLabels[key] }}</span><strong>{{
            number(metrics.project?.[key])
          }}</strong>
        </div>
      </div>
      <div class="grid">
        <section class="card">
          <h2>Освоенный объём</h2>
          <BarChart
            :items="
              ['bac', 'pv', 'ev', 'ac'].map((key) => ({
                label: metricLabels[key],
                value: metrics.project?.[key] || 0,
              }))
            "
          />
        </section>
        <section class="card">
          <h2>Состояние проекта</h2>
          <p>{{ project.description }}</p>
          <dl class="definition">
            <template v-for="key in ['spi', 'cpi', 's']" :key="key"
              ><dt>{{ metricLabels[key] }}</dt>
              <dd>{{ number(metrics.project?.[key], 2) }}</dd></template
            >
            <dt>Завершено задач</dt>
            <dd>
              {{ tasks.filter((t) => t.status === "done").length }} из
              {{ tasks.length }}
            </dd>
            <dt>Участников</dt>
            <dd>{{ members.length }}</dd>
          </dl>
        </section>
      </div></template
    ><template v-if="['plan', 'board'].includes(tab)"
      ><div class="page-head workbench-head">
        <div class="workbench-title">
          <h2>{{ tab === "board" ? "Доска задач" : "Календарный план" }}</h2>
        </div>
        <div
          v-if="tab === 'plan'"
          class="toolbar workbench-view"
          role="group"
          aria-label="Вид календарного плана"
        >
          <button
            v-if="tab === 'plan'"
            :class="{ primary: view === 'table' }"
            @click="view = 'table'"
          >
            Таблица</button
          ><button
            v-if="tab === 'plan'"
            :class="{ primary: view === 'gantt' }"
            @click="view = 'gantt'"
          >
            Гант
          </button>
        </div>
        <div v-if="editable" class="toolbar workbench-actions">
          <button @click="newRelease">＋ Релиз</button
          ><button class="primary" @click="newTask('backlog')">＋ Задача</button
          ><button
            v-if="tab === 'plan'"
            @click="
              ui.act(
                () =>
                  download(
                    `/projects/${id}/export/plan.xlsx`,
                    'Календарный план.xlsx',
                  ),
                '',
              )
            "
          >
            XLSX</button
          ><button
            v-if="tab === 'plan'"
            @click="
              ui.act(
                () =>
                  download(
                    `/projects/${id}/export/plan.pdf`,
                    'Календарный план.pdf',
                  ),
                '',
              )
            "
          >
            PDF
          </button>
        </div>
      </div>
      <div class="workbench-stats" aria-label="Сводка задач">
        <article>
          <span>Всего задач</span><strong>{{ taskStats.total }}</strong
          >
        </article>
        <article>
          <span>В работе</span><strong>{{ taskStats.active }}</strong
          >
        </article>
        <article>
          <span>Завершено</span><strong>{{ taskStats.done }}</strong
          >
        </article>
        <article>
          <span>Срок истёк</span><strong>{{ taskStats.overdue }}</strong
          >
        </article>
      </div>
      <div class="workbench-filters">
        <label class="task-search"
          ><svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
            <circle cx="8.5" cy="8.5" r="5.5" />
            <path d="m13 13 4 4" /></svg
          ><input
            v-model="taskSearch"
            type="search"
            placeholder="Найти задачу…"
            aria-label="Поиск задач"
        /></label>
        <SearchSelect v-model="assignee" :options="[{value:'',label:'Все исполнители'}, {value:'unassigned',label:'Без исполнителя'}, ...taskAssignees.map(person => ({value:String(person.user_id),label:person.full_name}))]" aria-label="Исполнитель" />
        <SearchSelect v-model="release" aria-label="Релиз" :options="[{value:'',label:'Все релизы'}, ...releases.map(r => ({value:r.release_id,label:r.name}))]" />
        <button
          type="button"
          class="risk-filter"
          :class="{ selected: riskOnly }"
          :aria-pressed="riskOnly"
          @click="riskOnly = !riskOnly"
        >
          <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
            <path d="M10 3 18 17H2L10 3Z" />
            <path d="M10 8v4m0 2v.5" /></svg
          >С рисками
        </button>
        <button
          v-if="hasTaskFilters"
          type="button"
          class="reset-filters"
          @click="resetTaskFilters"
        >
          Сбросить
        </button>
        <span class="filter-result" aria-live="polite"
          >Задачи {{ matchingTasks.length }} из {{ tasks.length }}</span
        >
      </div>
      <div
        v-if="tab === 'board'"
        class="status-filter"
        role="group"
        aria-label="Статусы задач"
      >
        <button
          v-for="(label, status) in taskStatuses"
          :key="status"
          :class="{ selected: boardStatuses.includes(status) }"
          :aria-pressed="boardStatuses.includes(status)"
          @click="
            boardStatuses = boardStatuses.includes(status)
              ? boardStatuses.filter((s) => s !== status)
              : [...boardStatuses, status]
          "
        >
          {{ label }}</button><button
          v-if="boardStatuses.length"
          @click="boardStatuses = []"
        >
          Все статусы
        </button>
      </div>
      <details v-if="releases.length" class="release-panel">
        <summary>
          Релизы проекта <span>{{ releases.length }}</span>
        </summary>
        <div class="releases">
          <article v-for="r in releases" :key="r.release_id" class="release">
            <button class="link" @click="release = r.release_id">
              {{ r.name }}</button><small>{{ date(r.release_date) }}</small
            ><small
              >{{
                tasks.filter(
                  (t) => t.release_id === r.release_id && t.status === "done",
                ).length
              }}
              из
              {{ tasks.filter((t) => t.release_id === r.release_id).length }}
              задач</small
            ><button
              v-if="editable"
              class="small"
              @click="
                form = { ...r };
                dialog = 'release';
              "
            >
              Изменить
            </button>
          </article>
        </div>
      </details>
      <KanbanBoard
        v-if="tab === 'board'"
        :tasks="visible"
        :indicators="indicators.tasks"
        :can-edit="canEditTask"
        :can-create="editable"
        :visible-statuses="boardStatuses"
        @open="selected = $event"
        @move="move"
        @create="newTask"
      /><GanttView
        v-else-if="view === 'gantt'"
        :tasks="visible"
        :editable="editable"
        :indicators="indicators.tasks"
        @open="selected = $event"
        @dates="dates"
        @progress="progress"
      />
      <div v-else class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Задача</th>
              <th>Статус</th>
              <th>Начало</th>
              <th>Окончание</th>
              <th>Прогресс</th>
              <th>План / факт, ч</th>
              <th>Исполнители</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="t in visible"
              :key="t.task_id"
              :class="{ 'risk-row': indicators.tasks?.[t.task_id]?.length }"
            >
              <td>
                <button class="link task-tree-label" :style="{ paddingLeft: `${taskDepth(t, tasks) * 20}px` }" @click="selected = t">
                  <span class="task-tree-number">{{ t.wbs || taskNumber(t) }}</span><span v-if="t.is_milestone" class="milestone-label">◆ </span>{{ t.name }}</button
                ><RiskBadge :risks="indicators.tasks?.[t.task_id] || []" />
              </td>
              <td>
                <span class="badge" :class="t.status">{{
                  taskStatuses[t.status]
                }}</span>
              </td>
              <td class="nowrap">{{ date(t.start_date) }}</td>
              <td class="nowrap">{{ date(t.due_date) }}</td>
              <td>
                <div class="progress">
                  <span :style="{ width: taskProgress(t) + '%' }" />
                </div>
                {{ taskProgress(t) }}%
              </td>
              <td>
                {{ number(t.planned_hours) }} / {{ number(t.actual_hours) }}
              </td>
              <td>
                {{
                  t.assignments?.map((a) => a.full_name).join(", ") ||
                  "Не назначены"
                }}
              </td>
            </tr>
          </tbody>
        </table>
        <p v-if="!visible.length" class="empty">
          {{
            hasTaskFilters
              ? "По этим условиям задач не найдено"
              : "Задач пока нет"
          }}
        </p>
      </div> </template
    ><ResourcePlan
      v-if="tab === 'resources'"
      :project-id="id"
      :indicators="indicators.users"
      :task-indicators="indicators.tasks"
      :focus-user="Number(route.query.user) || undefined"
      @saved="load"
    />
    <section v-if="tab === 'summary'" class="card project-team-card">
      <div class="page-head">
        <h2>Команда проекта</h2>
        <div class="toolbar">
          <span class="badge">{{ members.length }} участников</span>
          <button v-if="auth.admin" @click="editProject">
            Сменить руководителя
          </button>
        </div>
      </div>
      <div v-if="members.length" class="table-wrap team-table">
        <table>
          <thead>
            <tr>
              <th>Сотрудник</th>
              <th>Роль в проекте</th>
              <th>Должность в организации</th>
              <th class="num">Остаток работ, ч</th>
              <th v-if="editable" class="team-actions">Действия</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="u in members"
              :key="u.user_id"
              :class="{ 'risk-row': indicators.users?.[u.user_id]?.length }"
            >
              <td>
                <strong>{{ u.full_name }}</strong>
                <RiskBadge :risks="indicators.users?.[u.user_id] || []" />
              </td>
              <td>
                {{
                  u.user_id === project.manager_id
                    ? "Руководитель проекта"
                    : "Сотрудник"
                }}
              </td>
              <td>{{ u.job_title || "Не указана" }}</td>
              <td class="num">
                {{
                  number(
                    metrics.members?.find((m) => m.user_id === u.user_id)?.w,
                  )
                }}
              </td>
              <td v-if="editable" class="team-actions">
                <button
                  v-if="u.user_id !== project.manager_id"
                  class="small danger"
                  @click="removeMember(u)"
                >
                  Исключить
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="empty">В проект пока не добавлены участники</p>
      <form v-if="editable" class="team-add-form" @submit.prevent="addMember">
        <label
          >Добавить сотрудника в команду
          <SearchSelect v-model="memberId" :options="users.filter(u => u.role === 'employee' &amp;&amp; !members.some(m => m.user_id === u.user_id)).map(u => ({value:u.user_id,label:u.full_name}))" placeholder="Выберите сотрудника" required />
        </label>
        <button class="primary" :disabled="!memberId">Добавить</button>
      </form>
    </section>
    <RiskRegistry v-if="tab === 'risks'" :project-id="id" embedded /><template v-if="tab === 'labor'">
      <div class="page-head">
        <h2>Трудозатраты проекта</h2>
        <RouterLink v-if="auth.manager" :to="laborReportLocation">Открыть отчёт по трудозатратам</RouterLink>
      </div>
      <div class="filters labor-filters">
        <label>Сотрудник<SearchSelect v-model="laborUser" :options="[{value:'',label:'Все сотрудники'}, ...laborPeople.map(([value,label]) => ({value,label}))]" /></label>
        <label>Задача<SearchSelect v-model="laborTask" :options="[{value:'',label:'Все задачи'}, ...taskHierarchy(tasks).map(task => ({value:task.task_id,label:taskLabel(task,tasks)}))]" /></label>
        <label>С даты<input v-model="laborFrom" type="date" :max="laborTo || undefined" /></label>
        <label>По дату<input v-model="laborTo" type="date" :min="laborFrom || undefined" /></label>
        <button @click="laborUser = ''; laborTask = ''; laborFrom = ''; laborTo = ''">Сбросить</button>
      </div>
      <p v-if="laborFrom && laborTo && laborFrom > laborTo" class="alert error">Начало периода должно быть не позже окончания</p>
      <p v-else-if="laborBusy" class="loading">Загружаем трудозатраты…</p>
      <template v-else>
        <p class="labor-total">Списано по выбранным фильтрам <strong>{{ number(laborTotal, 2) }} ч</strong></p>
        <TimeEntryGroups v-if="filteredLabor.length" :entries="filteredLabor" />
        <p v-else class="empty">По выбранным фильтрам списаний нет</p>
      </template>
    </template>
    <TaskCard
      v-if="selected"
      :task="selected"
      :project-id="id"
      :tasks="tasks"
      :members="members"
      :releases="releases"
      :risks="indicators.tasks?.[selected.task_id] || []"
      :editable="editable"
      @saved="load"
      @close="selected = null"
    /><Modal
      v-if="dialog"
      :title="
        dialog === 'task'
          ? 'Новая задача'
          : dialog === 'release'
            ? 'Релиз'
            : 'Параметры проекта'
      "
      @close="dialog = ''"
      ><form @submit.prevent="save">
        <label>Название<input v-model="form.name" required /></label
        ><label>Описание<textarea v-model="form.description" /></label>
        <div class="form-grid">
          <template v-if="dialog !== 'release'"
            ><label
              >Начало<input
                type="date"
                v-model="form.start_date"
                required /></label
            ><label
              >Окончание<input
                type="date"
                v-model="form[dialog === 'project' ? 'end_date' : 'due_date']"
                :min="form.start_date"
                :disabled="form.is_milestone"
                required /></label></template
          ><label v-else
            >Дата релиза<input
              type="date"
              v-model="form.release_date"
              required /></label
          ><template v-if="dialog === 'project'"
            ><label v-if="auth.admin"
              >Руководитель проекта<SearchSelect v-model="form.manager_id" :options="managers.map(u => ({value:u.user_id,label:u.full_name}))" placeholder="Выберите руководителя" required /></label
            >
            <label v-else
              >Руководитель проекта<input
                :value="project.manager_name"
                readonly
            /></label>
            <label
              >Статус<SearchSelect v-model="form.status" :options="Object.entries(projectStatuses).map(([value,label]) => ({value,label}))" /></label
            ><label
              >Плановый объём, ч<input
                type="number"
                step="0.01"
                min="0"
                v-model.number="form.planned_hours" /></label></template
          ><template v-if="dialog === 'task'"
            ><label
              >Статус<SearchSelect v-model="form.status" :options="Object.entries(taskStatuses).map(([value,label]) => ({value,label}))" /></label
            ><label
              >Родительская задача<SearchSelect v-model="form.parent_task_id" :options="[{value:null,label:'Верхний уровень'}, ...taskHierarchy(tasks).filter(t => !t.is_milestone).map(t => ({value:t.task_id,label:taskLabel(t,tasks)}))]" /></label
            ><label
              >Релиз<SearchSelect v-model="form.release_id" :options="[{value:null,label:'Без релиза'}, ...releases.map(r => ({value:r.release_id,label:r.name}))]" /></label
            ><label class="check"
              ><input type="checkbox" v-model="form.is_milestone" />Контрольная
              точка (веха)</label
            ></template
          >
        </div>
        <label v-if="changingManager" class="check manager-change-confirmation">
          <input v-model="managerChangeConfirmed" type="checkbox" required />
          Подтверждаю назначение
          {{ managers.find((u) => u.user_id === form.manager_id)?.full_name }}.
          {{ project.manager_name }} покинет команду проекта.
        </label>
        <div class="toolbar">
          <button class="primary">Сохранить</button
          ><button
            v-if="dialog === 'release' && form.release_id"
            type="button"
            class="danger"
            @click="deleteRelease"
          >
            Удалить релиз
          </button>
        </div>
      </form></Modal
    ></template
  >
  <p v-else class="empty">Проект недоступен</p>
</template>

<style scoped>
.workbench-head {
  gap: 12px;
  margin: 24px 0 16px;
  align-items: center;
  flex-wrap: wrap;
}
.workbench-title {
  margin-right: auto;
}
.workbench-title h2 {
  margin: 0;
  color: var(--text);
  font-size: 20px;
  font-weight: 500;
  letter-spacing: 0;
}
.workbench-title p {
  margin: 4px 0 0;
  color: var(--muted);
  font-size: 12px;
}
.workbench-head .toolbar {
  margin: 0;
  gap: 8px;
}
.workbench-view {
  padding: 4px;
  background: var(--inset);
  border: 1px solid var(--border);
  border-radius: 8px;
}
.workbench-view button {
  border: 0;
  min-height: 32px;
  padding: 4px 12px;
  background: transparent;
  font-size: 12px;
  color: var(--muted);
  border-radius: 4px;
}
.workbench-view button.primary {
  color: var(--accent);
  background: var(--card);
  box-shadow: none;
}
.workbench-actions button {
  min-height: 36px;
  border-radius: 8px;
  padding: 8px 12px;
  font-size: 13px;
}
.workbench-actions button.primary {
  background: var(--button-fill);
  border-color: var(--button-fill);
  color: var(--button-ink);
  box-shadow: none;
}
.workbench-filters {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
}
.workbench-filters select,
.workbench-filters button {
  width: auto;
  min-height: 2.5rem;
  height: 2.5rem;
  border-radius: 8px;
  font-size: 12px;
  background: var(--card);
}
.workbench-filters select {
  max-width: 210px;
  padding: 8px 28px 8px 12px;
  margin: 0;
}
.workbench-filters :deep(.search-select) { flex: 0 1 210px; width: 210px; min-width: 160px; padding: 0; }
.workbench-filters :deep(.search-select input) { font-size: 13px; min-height: 40px; }
.task-search {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 8px;
  flex: 1 1 230px;
  max-width: 340px;
  height: 2.5rem;
  padding: 0 12px;
  margin: 0;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 8px;
}
.task-search > svg {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  stroke: var(--muted);
  stroke-width: 1.5;
}
.task-search input {
  min-width: 0;
  height: auto;
  min-height: 0;
  width: 100%;
  padding: 0;
  margin: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  outline: none;
  box-shadow: none;
  font-size: 12px;
}
.task-search:focus-within {
  border-color: var(--accent);
  box-shadow: none;
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.risk-filter {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--muted);
  padding: 8px 12px;
}
.risk-filter svg {
  width: 18px;
  height: 18px;
  stroke: currentColor;
  stroke-width: 1.5;
}
.risk-filter.selected {
  color: var(--accent);
  background: var(--accent-soft);
  border-color: var(--border);
}
.reset-filters {
  border: 0;
  color: var(--muted);
  padding: 6px 8px;
}
.filter-result {
  margin-left: auto;
  font-size: 12px;
  color: var(--muted);
  white-space: nowrap;
}
.release-panel {
  margin: 0 0 16px;
  color: var(--muted);
  font-size: 12px;
}
.release-panel summary {
  cursor: pointer;
  padding: 4px 0;
  width: max-content;
}
.release-panel summary > span {
  padding: 2px 6px;
  margin-left: 4px;
  background: var(--inset);
  border-radius: 4px;
  font-size: 12px;
}
.release-panel .releases {
  margin-top: 8px;
  margin-bottom: 0;
}
.release-panel .release {
  border-radius: 8px;
  background: var(--card);
}
.workbench-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  margin: 0 0 20px;
}
.workbench-stats article {
  position: relative;
  min-width: 0;
  padding: 20px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--card);
}
.workbench-stats article > span {
  display: block;
  color: var(--muted);
  font-size: 12px;
  margin-bottom: 4px;
}
.workbench-stats strong {
  font-size: 28px;
  font-weight: 500;
  line-height: 1.2;
  letter-spacing: 0;
  color: var(--text);
  font-variant-numeric: tabular-nums;
}
@media (max-width: 800px) {
  .workbench-title {
    width: 100%;
  }
  .workbench-head .workbench-actions {
    margin-left: auto;
  }
  .workbench-stats {
    gap: 12px;
  }
  .workbench-stats article {
  padding: 20px;
    border-radius: 12px;
}
}
@media (max-width: 600px) {
  .workbench-filters {
    gap: 8px;
  }
  .task-search {
    max-width: none;
    flex-basis: 100%;
  }
  .workbench-filters :deep(.search-select),
  .workbench-filters select {
    flex: 1;
    min-width: 0;
    max-width: calc(50% - 0.25rem);
    font-size: 12px;
  }
  .filter-result {
    font-size: 12px;
  }
  .workbench-stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .workbench-actions button {
  padding: 8px 12px;
  font-size: 13px;
    min-height: 36px;
}
}
.project-team-card {
  margin-top: 24px;
}
.project-team-card .page-head {
  margin: 0 0 16px;
}
.team-table {
  margin-bottom: 16px;
}
.team-table table {
  min-width: 550px;
}
.team-table th,
.team-table td {
  padding: 12px 16px;
}
.manager-change-confirmation {
  margin: 16px 0;
}
.team-actions {
  text-align: right;
  white-space: nowrap;
}
.team-add-form {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
}
.team-add-form label {
  flex: 1;
  max-width: 30rem;
}
@media (max-width: 600px) {
  .team-add-form {
    flex-direction: column;
    align-items: stretch;
  }
  .team-add-form label {
    max-width: none;
  }
  .project-team-card {
    padding: 16px;
  }
}

.task-tree-label { display: inline-block; }
.task-tree-number { display: inline-block; color: var(--muted); margin-right: 8px; font-variant-numeric: tabular-nums; }
.labor-filters { display: grid; grid-template-columns: minmax(160px, 1fr) minmax(200px, 1.4fr) 160px 160px auto; align-items: end; }
.labor-total { display: flex; align-items: baseline; gap: 12px; color: var(--secondary); }
.labor-total strong { color: var(--text); font-variant-numeric: tabular-nums; }
@media (max-width: 1200px) { .labor-filters { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 600px) { .labor-filters { grid-template-columns: 1fr; } }
</style>
