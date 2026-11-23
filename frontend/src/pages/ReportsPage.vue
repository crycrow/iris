<script setup>
import { ref, onMounted, computed, watch, nextTick } from "vue";
import { useRoute } from "vue-router";
import { api, download } from "../common/api/client.js";
import { useAuth } from "../common/stores/auth.js";
import { useUi } from "../common/stores/ui.js";
import {
  list,
  date,
  today,
  severities,
  riskStatuses,
  taskStatuses,
} from "../common/utils/format.js";
import {
  palette,
  taskColors,
  severityColors,
  statusColors,
  chartNumber,
  groupedCounts,
  monthlyLabel,
} from "../common/utils/reportCharts.js";
import SearchSelect from "../common/components/SearchSelect.vue";
import Modal from "../common/components/Modal.vue";
import TrendChart from "../common/components/TrendChart.vue";
import DistributionChart from "../common/components/DistributionChart.vue";
import ComparisonChart from "../common/components/ComparisonChart.vue";

const route = useRoute(),
  ui = useUi(),
  auth = useAuth();
const projects = ref([]),
  projectId = ref(""),
  data = ref(null),
  tasks = ref([]),
  analytics = ref(null),
  riskAnalysis = ref(null),
  scheduleForecast = ref(null),
  employeeId = ref(""),
  reportPeople = ref([]);
let resetting = false;
const kind = computed(() => route.params.kind || "labor");
const currentMonth = today().slice(0, 7);
const monthEnd = new Date(
  Number(currentMonth.slice(0, 4)),
  Number(currentMonth.slice(5)),
  0,
).getDate();
const periods = {
  labor: { from: currentMonth + "-01", to: currentMonth + "-" + monthEnd },
  risks: { from: "", to: "" },
};
const initialPeriod = periods[kind.value] || periods.labor;
const periodFrom = ref(initialPeriod.from),
  periodTo = ref(initialPeriod.to);
const appliedPeriod = ref({ from: periodFrom.value, to: periodTo.value });
function periodQuery() {
  const params = new URLSearchParams();
  if (appliedPeriod.value.from)
    params.set("date_from", appliedPeriod.value.from);
  if (appliedPeriod.value.to) params.set("date_to", appliedPeriod.value.to);
  if (kind.value === "labor" && employeeId.value) params.set("user_id", String(employeeId.value));
  return params.toString();
}
async function applyPeriod() {
  await ui.act(async () => {
    if (
      (kind.value !== "risks" && (!periodFrom.value || !periodTo.value)) ||
      (periodFrom.value && periodTo.value && periodFrom.value > periodTo.value)
    )
      throw new Error("Проверьте начало и окончание периода");
    appliedPeriod.value = { from: periodFrom.value, to: periodTo.value };
    periods[kind.value] = { ...appliedPeriod.value };
    await load();
  }, "");
}
async function currentPeriod() {
  periodFrom.value = currentMonth + "-01";
  periodTo.value = currentMonth + "-" + monthEnd;
  await applyPeriod();
}
async function allPeriod() {
  periodFrom.value = "";
  periodTo.value = "";
  await applyPeriod();
}
const loading = ref(false),
  analyticsError = ref(null),
  analyticsLoading = ref(false),
  riskStatus = ref(""),
  riskSeverity = ref(""),
  detail = ref(null);
let request = 0;
const reportProjects = computed(() =>
  projects.value.filter(
    (p) =>
      kind.value === "risks" ||
      auth.user?.role !== "manager" ||
      Number(p.manager_id) === Number(auth.user.user_id),
  ),
);
const hasReport = computed(() =>
  kind.value === "risks" ? riskAnalysis.value !== null : data.value !== null,
);
const projectOptions = computed(() => [
  { value: "", label: kind.value === "risks" ? "Все доступные проекты" : "Выберите проект" },
  ...reportProjects.value.map(p => ({ value: p.project_id, label: p.name })),
]);
const riskStatusOptions = [
  { value: "", label: "Все состояния" },
  ...Object.entries(riskStatuses).map(([value, label]) => ({ value, label })),
];
const riskSeverityOptions = [
  { value: "", label: "Все уровни" },
  ...Object.entries(severities).map(([value, label]) => ({ value, label })),
];
const titles = {
  labor: "Трудозатраты",
  risks: "Риски и реагирование",
  summary: "Сводка по проекту",
};
const project = computed(() =>
  projects.value.find((p) => Number(p.project_id) === Number(projectId.value)),
);
const metrics = computed(() => data.value?.project || {});
const monthly = computed(() => analytics.value?.monthly || []);
const employees = computed(() =>
  [...(analytics.value?.employees || [])].sort(
    (a, b) => a.full_name.localeCompare(b.full_name, "ru"),
  ),
);
const employeeOptions = computed(() => {
  const people = new Map([...(project.value?.members || []), ...reportPeople.value].map(p => [p.user_id, p]));
  return [{ value: "", label: "Все сотрудники" }, ...[...people.values()]
    .sort((a, b) => a.full_name.localeCompare(b.full_name, "ru"))
    .map(p => ({ value: p.user_id, label: p.full_name }))];
});
const riskImpact = computed(() => scheduleForecast.value?.risk_impact);
function selectRouteFilters() {
  const requestedProject = Number(route.query.project);
  projectId.value = reportProjects.value.some(p => Number(p.project_id) === requestedProject)
    ? requestedProject
    : kind.value === "risks" ? "" : reportProjects.value[0]?.project_id || "";
  employeeId.value = kind.value === "labor" && Number(route.query.user) > 0
    ? Number(route.query.user) : "";
  const selected = { ...(periods[kind.value] || periods.labor) };
  const isoDate = /^\d{4}-\d{2}-\d{2}$/;
  if (kind.value === "labor") {
    if (isoDate.test(String(route.query.from || ""))) selected.from = route.query.from;
    if (isoDate.test(String(route.query.to || ""))) selected.to = route.query.to;
  }
  periodFrom.value = selected.from;
  periodTo.value = selected.to;
  appliedPeriod.value = { ...selected };
}
async function changeProject() {
  employeeId.value = "";
  reportPeople.value = [];
  await ui.act(load, "");
}
async function resetFilters() {
  resetting = true;
  projectId.value = kind.value === "risks" ? "" : reportProjects.value[0]?.project_id || "";
  employeeId.value = "";
  reportPeople.value = [];
  riskStatus.value = "";
  riskSeverity.value = "";
  const period = kind.value === "risks" ? { from: "", to: "" } : { from: currentMonth + "-01", to: currentMonth + "-" + monthEnd };
  periodFrom.value = period.from;
  periodTo.value = period.to;
  appliedPeriod.value = { ...period };
  periods[kind.value] = { ...period };
  await nextTick();
  resetting = false;
  await ui.act(load, "");
}
const totals = computed(
  () => analytics.value?.totals || { planned_hours: null, actual_hours: null },
);
const asOf = computed(() => analytics.value?.as_of || today());
const parentIds = computed(
  () => new Set(tasks.value.map((t) => t.parent_task_id).filter(Boolean)),
);
const leafTasks = computed(() =>
  tasks.value.filter(
    (t) =>
      !parentIds.value.has(t.task_id) &&
      !t.is_milestone &&
      t.status !== "cancelled",
  ),
);
const pending = computed(() =>
  leafTasks.value
    .filter((t) => t.status !== "done")
    .sort((a, b) => a.due_date.localeCompare(b.due_date)),
);
const completion = computed(() =>
  leafTasks.value.length
    ? Math.round(
        (leafTasks.value.filter((t) => t.status === "done").length /
          leafTasks.value.length) *
          1000,
      ) / 10
    : 0,
);
const milestones = computed(() =>
  tasks.value
    .filter((t) => t.is_milestone && t.status !== "cancelled")
    .sort((a, b) => a.due_date.localeCompare(b.due_date)),
);
const taskStates = computed(() =>
  groupedCounts(leafTasks.value, "status", taskStatuses, taskColors).filter(
    (s) => s.value,
  ),
);
const riskTotals = computed(() => riskAnalysis.value?.totals || {});
const riskTypes = computed(() => riskAnalysis.value?.types || []);
const owners = computed(() => riskAnalysis.value?.owners || []);
const dailyChart = computed(() => analytics.value?.chart_granularity === "day");
const daily = computed(() => analytics.value?.daily || []);
const taskEffort = computed(() =>
  (analytics.value?.task_distribution || []).map((row) => ({
    key: row.task_id,
    label: row.name,
    value: row.actual_hours,
    color: palette.blue,
  })),
);
const daySeries = computed(() => [
  {
    label: "План за период",
    color: palette.slate,
    values: daily.value.map((d) => d.planned_hours),
  },
  {
    label: "Фактически учтено",
    color: palette.blue,
    values: daily.value.map((d) => d.actual_hours),
  },
]);
const monthSeries = computed(() => [
  {
    label: "План за период",
    color: palette.slate,
    values: monthly.value.map((m) => m.planned_hours),
  },
  {
    label: "Фактически учтено",
    color: palette.blue,
    values: monthly.value.map((m) => m.actual_hours),
  },
]);
const riskTimeline = computed(
  () =>
    riskAnalysis.value?.charts?.timeline || {
      title: "Выявление рисков",
      points: [],
    },
);
const riskPoints = computed(() => riskTimeline.value.points);
const riskSeverities = computed(() =>
  (riskAnalysis.value?.charts?.severities || []).map((r) => ({
    ...r,
    color: severityColors[r.key],
  })),
);
const riskStates = computed(() =>
  (riskAnalysis.value?.charts?.statuses || []).map((r) => ({
    ...r,
    color: statusColors[r.key],
  })),
);
const frequentRisks = computed(() => riskAnalysis.value?.charts?.types || []);
const deadlineText = computed(() =>
  scheduleForecast.value?.is_completed
    ? "Проект завершён"
    : scheduleForecast.value?.forecast_date
      ? scheduleForecast.value.delay_days > 0
        ? `Задержка ${chartNumber(scheduleForecast.value.delay_days)} раб. дн.`
        : "Завершение в пределах плана"
      : "Недостаточно данных для прогноза",
);
const kpis = computed(() =>
  kind.value === "labor"
    ? [
        {
          label: "Запланировано за период",
          value: totals.value.planned_hours,
          unit: "ч",
        },
        {
          label: "Учтено за период",
          value: totals.value.actual_hours,
          unit: "ч",
        },
        {
          label: "Сотрудников с трудозатратами",
          value: employees.value.filter((e) => e.actual_hours > 0).length,
        },
        {
          label: "Дней с записями",
          value:
            analytics.value?.daily?.filter((d) => d.actual_hours > 0).length ??
            null,
        },
      ]
    : kind.value === "risks"
      ? [
          { label: "Открыто рисков", value: riskTotals.value.open },
          {
            label: "Критических открыто",
            value: riskTotals.value.critical,
            color: palette.red,
          },
          {
            label: "Без ответственного",
            value: riskTotals.value.unassigned,
            color: palette.amber,
          },
          {
            label: "Закрыто рисков",
            value: riskTotals.value.closed,
            color: palette.teal,
          },
        ]
      : [
          { label: "Завершено задач", value: completion.value, unit: "%" },
          {
            label: "Просрочено задач",
            value: pending.value.filter((t) => t.due_date < asOf.value).length,
            color: palette.red,
          },
          {
            label: "Прогноз сдвига срока",
            value: scheduleForecast.value?.delay_days,
            unit: "раб. дн.",
          },
          {
            label: "Прогноз итоговых трудозатрат",
            value: metrics.value.eac,
            unit: "ч",
          },
        ],
);
const monthlyEmpty = computed(() =>
  analyticsError.value
    ? "Месячные данные не загружены"
    : "В проекте пока нет месячного плана и записей времени",
);
const historyFailure = computed(() =>
  analyticsError.value?.status === 404
    ? "Сервис истории недоступен. Возможно, запущена предыдущая версия сервера."
    : analyticsError.value?.status === 503
      ? "Сервис отчётов временно недоступен. Дождитесь его запуска."
      : "Не удалось загрузить историю. Это ошибка запроса, повторите загрузку.",
);

async function fetchAnalytics(id) {
  try {
    const value = await api.get(
      `/projects/${id}/analytics${kind.value === "labor" ? "?" + periodQuery() : ""}`,
    );
    if (
      !value ||
      ![value.monthly, value.employees, value.weekly].every(Array.isArray)
    )
      throw new Error("Некорректный ответ сервера");
    return { data: value, error: null };
  } catch (error) {
    return { data: null, error };
  }
}
async function retryAnalytics() {
  const current = request,
    id = projectId.value;
  if (!id || analyticsLoading.value) return;
  analyticsLoading.value = true;
  const result = await fetchAnalytics(id);
  if (current !== request || id !== projectId.value) return;
  analytics.value = result.data;
  analyticsError.value = result.error;
  analyticsLoading.value = false;
}
function riskQuery() {
  const params = new URLSearchParams(periodQuery());
  if (projectId.value) params.set("project_id", String(projectId.value));
  if (riskStatus.value) params.set("status", riskStatus.value);
  if (riskSeverity.value) params.set("severity", riskSeverity.value);
  return params.toString();
}
async function load() {
  const current = ++request;
  data.value = null;
  tasks.value = [];
  analytics.value = null;
  riskAnalysis.value = null;
  scheduleForecast.value = null;
  analyticsError.value = null;
  analyticsLoading.value = false;
  detail.value = null;
  if (!projectId.value && kind.value !== "risks") {
    loading.value = false;
    return;
  }
  loading.value = true;
  try {
    if (kind.value === "risks") {
      const rows = await api.get(`/reports/risks?${riskQuery()}`);
      if (current === request) riskAnalysis.value = rows;
      return;
    }
    const [metricRows, taskRows, history, riskRows, forecast] =
      await Promise.all([
        api.get(`/projects/${projectId.value}/metrics`),
        api.get(`/projects/${projectId.value}/tasks`),
        fetchAnalytics(projectId.value),
        kind.value === "risks"
          ? api.get(`/reports/risks?${riskQuery()}`)
          : Promise.resolve(null),
        kind.value === "summary"
          ? api.get(`/projects/${projectId.value}/schedule-forecast`)
          : Promise.resolve(null),
      ]);
    if (current !== request) return;
    data.value = metricRows;
    tasks.value = list(taskRows);
    analytics.value = history.data;
    reportPeople.value = employeeId.value
      ? [...new Map([...reportPeople.value, ...(history.data?.employees || [])].map(p => [p.user_id, p])).values()]
      : history.data?.employees || [];
    analyticsError.value = history.error;
    riskAnalysis.value = riskRows;
    scheduleForecast.value = forecast;
  } finally {
    if (current === request) loading.value = false;
  }
}
onMounted(() =>
  ui.act(async () => {
    projects.value = list(await api.get("/projects"));
    selectRouteFilters();
    await load();
  }, ""),
);
watch([kind, () => route.query], () => {
  reportPeople.value = [];
  selectRouteFilters();
  ui.act(load, "");
});
watch([riskStatus, riskSeverity], () => {
  if (kind.value === "risks" && !resetting) ui.act(load, "");
});
function exportReport(format) {
  const path =
    kind.value === "risks"
      ? `/reports/risks/export.${format}?${riskQuery()}`
      : kind.value === "summary"
        ? `/projects/${projectId.value}/summary.${format}`
        : `/projects/${projectId.value}/export/labor.${format}?${periodQuery()}`;
  return ui.act(() => download(path, `${titles[kind.value]}.${format}`), "");
}
function showMonth(item) {
  if (dailyChart.value) {
    const day = daily.value[item.index];
    if (day)
      detail.value = {
        title: `Трудозатраты за ${date(day.work_date)}`,
        headers: ["Дата", "План, ч", "Учтено, ч"],
        rows: [
          [
            date(day.work_date),
            chartNumber(day.planned_hours),
            chartNumber(day.actual_hours),
          ],
        ],
      };
    return;
  }
  const month = monthly.value[item.index];
  if (!month) return;
  detail.value = {
    title: `Трудозатраты за ${monthlyLabel(month.month)}`,
    headers: ["Дата", "План, ч", "Учтено, ч"],
    rows: (analytics.value?.daily || [])
      .filter((d) => d.work_date.startsWith(month.month.slice(0, 7)))
      .map((d) => [
        date(d.work_date),
        chartNumber(d.planned_hours),
        chartNumber(d.actual_hours),
      ]),
    empty: "В этом месяце нет записей времени",
  };
}
function showTaskEffort(item) {
  const rows = analytics.value?.task_hours || [];
  const selected =
    item.key === null
      ? rows.slice(6)
      : rows.filter((row) => row.task_id === item.key);
  detail.value = {
    title: item.label,
    headers: ["Задача", "Учтено, ч", "Доля факта проекта, %"],
    rows: selected.map((row) => [
      row.name,
      chartNumber(row.actual_hours),
      chartNumber(row.share_pct),
    ]),
    empty: "Записей времени нет",
  };
}
function showState(item) {
  detail.value = {
    title: item.label,
    headers: ["Задача", "Срок", "Готовность, %"],
    rows: leafTasks.value
      .filter((t) => t.status === item.key)
      .map((t) => [t.name, date(t.due_date), chartNumber(t.progress_pct)]),
    empty: "Задач нет",
  };
}
function showRiskType(item) {
  detail.value = {
    title: item.name,
    headers: ["Показатель", "Значение"],
    rows: [
      ["Открыто", item.open],
      ["Критических", item.critical],
      ["Закрыто", item.closed],
      ["Рекомендуемое действие", item.recommendation],
    ],
    empty: "Данных нет",
  };
}
function showRiskGroup(title, rows) {
  detail.value = {
    title,
    headers: ["Категория", "Количество рисков"],
    rows: rows.map((r) => [r.label, r.value]),
    empty: "Данных нет",
  };
}
function showRiskPoint(item) {
  const point = riskPoints.value[item.index];
  if (point)
    detail.value = {
      title: "Выявленные риски",
      headers: ["Период выявления", "Количество рисков"],
      rows: [[point.full_label, point.detected]],
      empty: "Риски не выявлены",
    };
}
function showFrequentRisk(item) {
  const row = riskTypes.value.find((r) => r.name === item.key);
  if (row) showRiskType(row);
}
</script>

<template>
  <div class="reports-page">
    <div class="toolbar">
      <h1>{{ titles[kind] }}</h1>
      <div class="report-actions">
        <button
          :disabled="!hasReport || loading || (kind === 'labor' && !analytics)"
          @click="exportReport('xlsx')"
        >
          XLSX</button
        ><button
          :disabled="!hasReport || loading || (kind === 'labor' && !analytics)"
          @click="exportReport('pdf')"
        >
          PDF
        </button>
      </div>
    </div>
    <div class="card report-filters">
      <label class="project-filter">
        Проект
        <SearchSelect v-model="projectId" :options="projectOptions" aria-label="Проект" @change="changeProject" />
      </label>
      <label v-if="kind === 'labor'" class="employee-filter">
        Сотрудник
        <SearchSelect v-model="employeeId" :options="employeeOptions" placeholder="Все сотрудники"
          :disabled="!projectId || loading" aria-label="Сотрудник" @change="ui.act(load, '')" />
      </label>
      <button type="button" :disabled="loading" @click="resetFilters">Сбросить фильтры</button>
      <template v-if="kind === 'risks'">
        <label>
          Состояние
          <SearchSelect v-model="riskStatus" :options="riskStatusOptions" aria-label="Состояние риска" />
        </label>
        <label>
          Критичность
          <SearchSelect v-model="riskSeverity" :options="riskSeverityOptions" aria-label="Критичность риска" />
        </label>
      </template>
      <span v-if="data && kind === 'summary'" class="report-date"
        >На {{ date(asOf) }}</span
      >
      <form
        v-if="kind === 'labor' || kind === 'risks'"
        class="labor-period"
        @submit.prevent="applyPeriod"
      >
        <label
          >{{ kind === "risks" ? "Выявлены с" : "С даты"
          }}<input
            v-model="periodFrom"
            type="date"
            :max="periodTo"
            :required="kind !== 'risks'"
        /></label>
        <label
          >{{ kind === "risks" ? "Выявлены по" : "По дату"
          }}<input
            v-model="periodTo"
            type="date"
            :min="periodFrom"
            :required="kind !== 'risks'"
        /></label>
        <button class="primary" :disabled="loading">Показать</button>
        <button type="button" :disabled="loading" @click="currentPeriod">
          Текущий месяц
        </button>
        <button
          v-if="kind === 'risks'"
          type="button"
          :disabled="loading"
          @click="allPeriod"
        >
          Весь период
        </button>
      </form>
    </div>
    <p v-if="loading" role="status" class="empty">Загрузка отчёта</p>
    <template v-else-if="hasReport">
      <div class="report-kpis">
        <div
          v-for="kpi in kpis"
          :key="kpi.label"
          class="report-kpi"
          :style="{ '--kpi-color': kpi.color || 'var(--text)' }"
        >
          <span>{{ kpi.label }}</span><strong
            >{{ chartNumber(kpi.value) }}
            <small v-if="kpi.unit">{{ kpi.unit }}</small></strong
          >
        </div>
      </div>
      <div
        v-if="analyticsError && kind === 'labor'"
        class="report-notice"
        :aria-busy="analyticsLoading"
      >
        <span>{{ historyFailure }}</span><button
          class="retry-analytics"
          :disabled="analyticsLoading"
          @click="retryAnalytics"
        >
          Повторить загрузку
        </button>
      </div>
      <template v-if="kind === 'labor'">
        <div class="report-charts labor-charts">
          <section class="card chart-card">
            <h2>
              {{
                dailyChart
                  ? "План и учтённые часы по дням"
                  : "План и учтённые часы по месяцам"
              }}
            </h2>
            <TrendChart
              :labels="
                dailyChart
                  ? daily.map((d) => date(d.work_date).slice(0, 5))
                  : monthly.map((m) => monthlyLabel(m.month))
              "
              :series="dailyChart ? daySeries : monthSeries"
              type="bar"
              :label="
                dailyChart
                  ? 'План и учтённые часы по дням'
                  : 'Трудозатраты по месяцам'
              "
              :empty-message="monthlyEmpty"
              @select="showMonth"
            />
          </section>

        </div>
        <section class="card report-table">
          <h2>Трудозатраты по месяцам</h2>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Месяц</th>
                  <th class="num">План за период, ч</th>
                  <th class="num">Фактически учтено, ч</th>
                  <th class="num">Разница, ч</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="m in monthly" :key="m.month">
                  <td>{{ monthlyLabel(m.month) }}</td>
                  <td class="num">{{ chartNumber(m.planned_hours) }}</td>
                  <td class="num">
                    {{
                      m.actual_hours === null
                        ? "—"
                        : chartNumber(m.actual_hours)
                    }}
                  </td>
                  <td class="num">
                    {{
                      m.actual_hours === null
                        ? "—"
                        : chartNumber(m.actual_hours - m.planned_hours)
                    }}
                  </td>
                </tr>
                <tr v-if="!monthly.length">
                  <td colspan="4" class="empty">{{ monthlyEmpty }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
          <section class="card chart-card">
            <h2>Трудозатраты по задачам</h2>
            <ComparisonChart
              :items="taskEffort"
              unit="ч"
              label="Факт по задачам"
              @select="showTaskEffort"
            />
          </section>
        <section class="card report-table">
          <h2>Трудозатраты сотрудников</h2>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Сотрудник</th>
                  <th class="num">Назначено, ч</th>
                  <th class="num">Учтено, ч</th>
                  <th class="num">Всего по всем проектам, ч</th>
                  <th class="num">Доля загрузки на проекте, %</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="e in employees" :key="e.user_id">
                  <td>{{ e.full_name }}</td>
                  <td class="num">{{ chartNumber(e.planned_hours) }}</td>
                  <td class="num">{{ chartNumber(e.actual_hours) }}</td>
                  <td class="num">{{ chartNumber(e.total_actual_hours) }}</td>
                  <td class="num">
                    {{
                      e.project_share_pct === null
                        ? "Нет списаний"
                        : chartNumber(e.project_share_pct) + " %"
                    }}
                  </td>
                </tr>
                <tr v-if="!employees.length">
                  <td colspan="5" class="empty">Данных по сотрудникам нет</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </template>
      <template v-else-if="kind === 'risks'">
        <div class="report-charts">
          <section class="card chart-card risk-timeline">
            <h2>{{ riskTimeline.title }}</h2>
            <TrendChart
              v-if="riskPoints.length > 1"
              type="line"
              unit="рисков"
              integer
              :height="240"
              :labels="riskPoints.map((point) => point.label)"
              :full-labels="riskPoints.map((point) => point.full_label)"
              :series="[
                {
                  label: 'Выявлено',
                  color: palette.blue,
                  values: riskPoints.map((point) => point.detected),
                },
              ]"
              :label="riskTimeline.title"
              @select="showRiskPoint"
            />
            <button
              v-else-if="riskPoints.length === 1"
              type="button"
              class="risk-single"
              @click="showRiskPoint({ index: 0 })"
            >
              <strong>{{ chartNumber(riskPoints[0].detected, 0) }}</strong>
              <span
                ><b>Выявлено рисков</b
                ><span>{{ riskPoints[0].full_label }}</span></span
              >
            </button>
            <p v-else class="risk-timeline-empty">
              В выбранном периоде риски не выявлены
            </p>
          </section>
          <section class="card chart-card">
            <h2>Критичность рисков</h2>
            <DistributionChart
              :items="riskSeverities"
              unit="рисков"
              label="Критичность рисков"
              @select="showRiskGroup('Критичность рисков', riskSeverities)"
            />
          </section>
          <section class="card chart-card">
            <h2>Состояния рисков</h2>
            <DistributionChart
              :items="riskStates"
              unit="рисков"
              label="Состояния рисков"
              @select="showRiskGroup('Состояния рисков', riskStates)"
            />
          </section>
          <section class="card chart-card chart-wide">
            <h2>Наиболее частые типы рисков</h2>
            <ComparisonChart
              :items="frequentRisks"
              unit="рисков"
              label="Наиболее частые типы рисков"
              @select="showFrequentRisk"
            />
          </section>
        </div>
        <section class="card report-table">
          <h2>Приоритеты реагирования</h2>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Тип риска</th>
                  <th class="num">Открыто</th>
                  <th class="num">Критических</th>
                  <th class="num">Закрыто</th>
                  <th>Рекомендуемое действие</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="r in riskTypes" :key="r.name">
                  <td>{{ r.name }}</td>
                  <td class="num">{{ r.open }}</td>
                  <td class="num">{{ r.critical }}</td>
                  <td class="num">{{ r.closed }}</td>
                  <td>{{ r.recommendation }}</td>
                </tr>
                <tr v-if="!riskTypes.length">
                  <td colspan="5" class="empty">
                    По выбранным условиям рисков нет
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
        <section class="card report-table">
          <h2>Работа ответственных</h2>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Ответственный</th>
                  <th class="num">Всего</th>
                  <th class="num">Открыто</th>
                  <th class="num">В работе</th>
                  <th class="num">Критических открыто</th>
                  <th class="num">Закрыто</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="r in owners" :key="r.user_id ?? 'unassigned'">
                  <td>{{ r.name }}</td>
                  <td class="num">{{ r.total }}</td>
                  <td class="num">{{ r.open }}</td>
                  <td class="num">{{ r.in_progress }}</td>
                  <td class="num">{{ r.critical }}</td>
                  <td class="num">{{ r.closed }}</td>
                </tr>
                <tr v-if="!owners.length">
                  <td colspan="6" class="empty">Данных нет</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </template>
      <template v-else>
        <section class="card project-dates">
          <div>
            <span>Начало проекта</span
            ><strong>{{ date(project?.start_date) }}</strong>
          </div>
          <div>
            <span>Плановое завершение</span
            ><strong>{{ date(project?.end_date) }}</strong>
          </div>
          <div>
            <span>Руководитель</span
            ><strong>{{ project?.manager_name || "Не назначен" }}</strong>
          </div>
        </section>
        <div class="report-charts summary-charts">
          <section class="card chart-card">
            <h2>Выполнение задач</h2>
            <DistributionChart
              :items="taskStates"
              unit="задач"
              label="Состояние задач проекта"
              @select="showState"
            />
          </section>
          <section class="card chart-card deadline-card">
            <h2>Срок завершения проекта</h2>
            <div class="deadline-dates">
              <div>
                <span>По плану</span
                ><strong>{{
                  date(scheduleForecast?.planned_date || project?.end_date)
                }}</strong>
              </div>
              <div>
                <span>По прогнозу</span
                ><strong>{{
                  scheduleForecast?.is_completed
                    ? "Завершён"
                    : scheduleForecast?.forecast_date
                      ? date(scheduleForecast.forecast_date)
                      : "Нет прогноза"
                }}</strong>
              </div>
            </div>
            <div
              class="deadline-status"
              :class="{ delayed: scheduleForecast?.delay_days > 0 }"
            >
              {{ deadlineText }}
            </div>
          </section>
        </div>
        <section class="card report-table">
          <h2>Контрольные точки</h2>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Контрольная точка</th>
                  <th>Срок</th>
                  <th>Состояние</th>
                  <th>Выполнение срока</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="t in milestones" :key="t.task_id">
                  <td class="milestone-label">◆ {{ t.name }}</td>
                  <td>{{ date(t.due_date) }}</td>
                  <td>{{ taskStatuses[t.status] }}</td>
                  <td>
                    {{
                      t.status === "done"
                        ? "Завершена"
                        : t.due_date < asOf
                          ? "Просрочена"
                          : "В плане"
                    }}
                  </td>
                </tr>
                <tr v-if="!milestones.length">
                  <td colspan="4" class="empty">Контрольные точки не заданы</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
        <section v-if="riskImpact" class="card report-table">
          <h2>Риски выполнения проекта</h2>
          <div class="report-kpis">
            <div class="report-kpi"><span>Незавершённых задач с рисками</span><strong>{{ riskImpact.tasks }}</strong></div>
            <div class="report-kpi"><span>Контрольных точек с рисками</span><strong>{{ riskImpact.milestones }}</strong></div>
            <div class="report-kpi"><span>Просроченных задач и вех с рисками</span><strong>{{ riskImpact.overdue }}</strong></div>
            <div class="report-kpi"><span>Рисков без ответственного</span><strong>{{ riskImpact.unassigned }}</strong></div>
          </div>
          <h3>Зоны, требующие решения</h3>
          <div class="table-wrap"><table>
            <thead><tr><th>Объект</th><th>Плановый срок</th><th class="num">Открыто</th><th class="num">Критических</th><th>Ответственные</th><th>Необходимое решение</th></tr></thead>
            <tbody>
              <tr v-for="zone in riskImpact.zones" :key="zone.risk_id">
                <td><RouterLink :to="zone.task_id ? `/projects/${projectId}?tab=plan&task=${zone.task_id}` : `/risks/${zone.risk_id}`">{{ zone.target }}</RouterLink></td>
                <td>{{ zone.deadline ? date(zone.deadline) : 'Не задан' }}</td>
                <td class="num">{{ zone.open }}</td><td class="num">{{ zone.critical }}</td>
                <td>{{ zone.owners }}</td><td>{{ zone.decision }}</td>
              </tr>
              <tr v-if="!riskImpact.zones.length"><td colspan="6" class="empty">Открытых рисков проекта нет</td></tr>
            </tbody>
          </table></div>
        </section>
        <section class="card report-table">
          <h2>Ближайшие работы</h2>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Задача</th>
                  <th>Срок</th>
                  <th>Состояние</th>
                  <th class="num">Готовность, %</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="t in pending.slice(0, 10)" :key="t.task_id">
                  <td>
                    <RouterLink
                      :to="`/projects/${projectId}?tab=plan&task=${t.task_id}`"
                      >{{ t.name }}</RouterLink
                    >
                  </td>
                  <td>{{ date(t.due_date) }}</td>
                  <td>{{ taskStatuses[t.status] }}</td>
                  <td class="num">{{ chartNumber(t.progress_pct) }}</td>
                </tr>
                <tr v-if="!pending.length">
                  <td colspan="4" class="empty">Незавершённых задач нет</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </template>
    </template>
    <p v-else class="empty">Выберите проект для отчёта</p>
    <Modal v-if="detail" :title="detail.title" @close="detail = null"
      ><div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th v-for="h in detail.headers" :key="h">{{ h }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, i) in detail.rows" :key="i">
              <td v-for="(v, j) in row" :key="j">{{ v }}</td>
            </tr>
            <tr v-if="!detail.rows.length">
              <td :colspan="detail.headers.length" class="empty">
                {{ detail.empty }}
              </td>
            </tr>
          </tbody>
        </table>
      </div></Modal
    >
  </div>
</template>

<style scoped>
.reports-page {
  min-width: 0;
}
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.report-actions {
  display: flex;
  gap: 8px;
}
.report-filters {
  display: flex;
  align-items: flex-end;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 20px;
  padding: 20px;
}
.report-filters label {
  flex: 1;
  min-width: 10rem;
}
.report-filters .project-filter {
  flex: 2;
}
.report-date {
  padding-bottom: 8px;
  white-space: nowrap;
}
.report-kpis {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 16px;
  margin-bottom: 20px;
}
.report-kpi {
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--card);
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.report-kpi > span {
  font-size: 13px;
  line-height: 1.4;
  color: var(--secondary);
}
.report-kpi strong {
  font-size: 28px;
  line-height: 1.25;
  font-variant-numeric: tabular-nums;
  font-weight: 500;
  color: var(--kpi-color);
}
.report-kpi small {
  font-size: 14px;
  font-weight: 400;
  color: var(--muted);
}
.employee-filter { min-width: 240px; flex: 1; }
.report-charts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px;
  margin-bottom: 20px;
}
.report-charts.labor-charts { grid-template-columns: minmax(0, 1fr); }
.chart-card {
  padding: 24px;
  min-width: 0;
  margin-bottom: 20px;
}
.report-charts .chart-card {
  margin: 0;
  padding: 24px;
}
h2 {
  margin: 0 0 20px;
  font-size: 18px;
}
.report-table {
  padding: 20px;
  margin-top: 20px;
}
.report-table .table-wrap {
  margin: 0;
}
.report-table th,
.report-table td {
  text-align: left;
  vertical-align: top;
  line-height: 1.5;
}
.report-table .num {
  text-align: right;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.project-dates {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 20px;
  padding: 20px;
}
.project-dates > div {
  display: grid;
  gap: 8px;
}
.project-dates span {
  font-size: 14px;
}
.project-dates strong {
  font-size: 18px;
}
.report-notice {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px;
  margin-bottom: 20px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--inset);
}
.report-notice button {
  flex: none;
}
@media (max-width: 850px) {
  .report-charts {
    grid-template-columns: 1fr;
  }
  .project-dates {
    grid-template-columns: 1fr;
  }
  .report-kpis {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 550px) {
  .toolbar {
    align-items: flex-start;
    flex-direction: column;
  }
  .report-filters {
    align-items: stretch;
    flex-direction: column;
  }
  .report-date {
    padding: 0;
  }
  .report-kpi {
  padding: 20px;
    gap: 8px;
}
  .report-kpi strong {
  font-size: 28px;
    font-weight: 500;
  color: var(--kpi-color);
}
  .chart-card,
  .report-table {
    padding: 16px;
  }
  .report-notice {
    flex-direction: column;
    align-items: stretch;
    background: var(--inset);
}
}
.labor-period {
  display: flex;
  align-items: flex-end;
  flex-wrap: wrap;
  gap: 12px;
  width: 100%;
  border-top: 1px solid var(--border);
  padding-top: 16px;
}
.labor-period label {
  flex: 1;
  min-width: 10rem;
}
.labor-period button {
  flex: none;
}
.labor-charts {
  grid-template-columns: 1fr;
}
.chart-wide {
  grid-column: 1/-1;
}
.deadline-dates {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin: 16px 0 32px;
}
.deadline-dates > div {
  padding: 20px;
  background: var(--inset);
  border-radius: 12px;
  display: grid;
  gap: 12px;
}
.deadline-dates strong {
  font-size: 26px;
}
.deadline-status {
  padding: 16px 20px;
  border-radius: 12px;
  background: var(--inset);
  font-weight: 500;
}
.deadline-status.delayed {
  color: var(--danger);
  background: color-mix(in srgb, var(--danger) 10%, var(--card));
}
@media (max-width: 550px) {
  .deadline-dates {
    grid-template-columns: 1fr;
  }
  .deadline-dates strong {
    font-size: 21px;
  }
  .labor-period button {
    width: 100%;
  }
}

.summary-charts {
  align-items: stretch;
}
.summary-charts .chart-card {
  display: flex;
  flex-direction: column;
  padding: 24px;
}
.summary-charts h2 {
  min-height: 1.5rem;
}
.summary-charts :deep(.distribution-chart) {
  flex: 1;
  min-height: 20rem;
}
.summary-charts .deadline-dates {
  flex: 1;
  align-content: center;
  margin: 0 0 20px;
}
.summary-charts .deadline-dates > div {
  min-width: 0;
}
.summary-charts .deadline-dates strong {
  font-size: clamp(1.15rem, 1.7vw, 1.6rem);
}
.summary-charts .deadline-status {
  margin-top: auto;
  min-height: 3rem;
  display: flex;
  align-items: center;
  background: var(--inset);
  font-weight: 500;
}
.risk-timeline {
  grid-column: 1 / -1;
}
.risk-single {
  display: inline-flex;
  align-items: center;
  gap: 20px;
  text-align: left;
  padding: 12px 20px;
  border: 1px solid var(--border);
  background: var(--card);
  border-radius: 12px;
  max-width: 100%;
}
.risk-single strong {
  font-size: 37px;
  color: var(--accent);
  font-variant-numeric: tabular-nums;
}
.risk-single > span {
  display: grid;
  gap: 6px;
}
.risk-single b {
  font-weight: 600;
}
.risk-single span span {
  color: var(--muted);
  overflow-wrap: anywhere;
}
.risk-timeline-empty {
  margin: 0;
  padding: 16px 0;
  color: var(--muted);
}
</style>
