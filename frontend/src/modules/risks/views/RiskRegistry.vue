<script setup>
import { taskHierarchy, taskLabel } from "../../time-tracking/taskFilters.js";
import SearchSelect from "../../../common/components/SearchSelect.vue";
import { ref, computed, onMounted, onBeforeUnmount, watch } from "vue";
import { api, download } from "../../../common/api/client.js";
import { useAuth } from "../../../common/stores/auth.js";
import { useUi } from "../../../common/stores/ui.js";
import {
  list,
  date,
  number,
  riskStatuses,
  severities,
} from "../../../common/utils/format.js";
import { useRoute, useRouter } from "vue-router";
import { riskObjectLocation } from "../../../common/utils/riskNavigation.js";
import Modal from "../../../common/components/Modal.vue";
const props = defineProps({ projectId: Number, embedded: Boolean });
const route = useRoute(),
  router = useRouter();
const auth = useAuth(),
  ui = useUi(),
  items = ref([]),
  projects = ref([]),
  types = ref([]),
  tasks = ref([]),
  show = ref(false),
  busy = ref(false),
  filters = ref(initialFilters()),
  form = ref({});
const active = computed(() =>
  items.value.filter((r) => !["closed", "rejected"].includes(r.status)),
);
function query() {
  const q = new URLSearchParams();
  Object.entries(filters.value).forEach(([k, v]) => {
    if (v)
      q.set(
        k === "from" ? "date_from" : k === "to" ? "date_to" : k,
        v === true ? "1" : v,
      );
  });
  return q.toString();
}
function defaults() {
  return {
    project_id: props.projectId || "",
    object_search: "",
    risk_type_id: "",
    status: "",
    severity: "",
    from: "",
    to: "",
    unviewed: false,
  };
}
function storageKey() {
  return `risk-filters:${auth.user?.user_id}:${props.projectId || "all"}`;
}
function initialFilters() {
  const base = defaults();
  let stored = {};
  try {
    stored = JSON.parse(sessionStorage.getItem(storageKey()) || "{}");
  } catch {}
  const hasQuery = Object.keys(route.query).some((key) =>
    key.startsWith("rf_"),
  );
  const result = { ...base, ...(!hasQuery ? stored : {}) };
  for (const key of Object.keys(base)) {
    const raw = route.query[`rf_${key}`];
    if (typeof raw === "string")
      result[key] = key === "unviewed" ? raw === "1" : raw;
  }
  result.project_id = props.projectId || "";
  if (result.status && !(result.status in riskStatuses)) result.status = "";
  if (result.severity && !(result.severity in severities)) result.severity = "";
  for (const key of ["from", "to"]) {
    const value = result[key];
    if (
      value &&
      (!/^\d{4}-\d{2}-\d{2}$/.test(value) ||
        Number(value.slice(0, 4)) < 1 ||
        !Number.isFinite(Date.parse(value)) ||
        new Date(value).toISOString().slice(0, 10) !== value)
    )
      result[key] = "";
  }
  if (result.from && result.to && result.from > result.to) {
    result.from = "";
    result.to = "";
  }
  return result;
}
function locationQuery() {
  const result = { ...route.query };
  for (const key of Object.keys(defaults())) {
    delete result[`rf_${key}`];
    const value = filters.value[key];
    if (value && !(key === "project_id" && props.projectId))
      result[`rf_${key}`] = value === true ? "1" : String(value);
  }
  result.rf_saved = "1";
  return result;
}
const returnUrl = computed(
  () => router.resolve({ path: route.path, query: locationQuery() }).fullPath,
);
let request = 0, filterTimer;
function scheduleFilters() {
  clearTimeout(filterTimer);
  filterTimer = setTimeout(() => ui.act(applyFilters, ""), 250);
}
onBeforeUnmount(() => clearTimeout(filterTimer));
async function load() {
  const current = ++request;
  const data = list(await api.get("/risks?" + query()));
  if (current === request) items.value = data;
}
async function applyFilters() {
  clearTimeout(filterTimer);
  if (
    filters.value.from &&
    filters.value.to &&
    filters.value.from > filters.value.to
  )
    throw new Error("Начало периода должно быть не позже окончания");
  sessionStorage.setItem(storageKey(), JSON.stringify(filters.value));
  await router.replace({ path: route.path, query: locationQuery() });
  await load();
}
async function resetFilters() {
  filters.value = defaults();
  await applyFilters();
}
watch(
  () => route.query,
  () => {
    if (
      route.path !== "/risks" &&
      !(props.embedded && route.query.tab === "risks")
    )
      return;
    const restored = initialFilters();
    if (JSON.stringify(restored) !== JSON.stringify(filters.value)) {
      filters.value = restored;
      ui.act(load, "");
    }
  },
);
onMounted(() =>
  ui.act(async () => {
    const [availableProjects, availableTypes] = await Promise.all([
      api.get("/projects"),
      api.get("/risk-types"),
    ]);
    projects.value = list(availableProjects);
    types.value = list(availableTypes);
    if (
      !props.projectId &&
      filters.value.project_id &&
      !projects.value.some(
        (project) =>
          String(project.project_id) === String(filters.value.project_id),
      )
    )
      filters.value.project_id = "";
    await applyFilters();
  }, ""),
);
async function scan() {
  busy.value = true;
  await ui.act(async () => {
    await api.post(
      "/risks/scan",
      filters.value.project_id
        ? { project_ids: [Number(filters.value.project_id)] }
        : {},
    );
    await load();
  }, "Анализ рисков завершён");
  busy.value = false;
}
async function loadTasks() {
  form.value.task_id = null;
  tasks.value = form.value.project_id
    ? taskHierarchy(list(await api.get(`/projects/${form.value.project_id}/tasks`)))
    : [];
}
function create() {
  form.value = {
    risk_type_id: types.value[0]?.risk_type_id,
    project_id: props.projectId || projects.value[0]?.project_id,
    task_id: null,
    severity: "medium",
    description: "",
  };
  show.value = true;
  ui.act(loadTasks, "");
}
async function save() {
  await ui.act(async () => {
    await api.post("/risks", {
      ...form.value,
      project_id: props.projectId || form.value.project_id,
    });
    show.value = false;
    await load();
  }, "Риск добавлен");
}
</script>
<template>
  <div class="page-head">
    <div>
      <h1 v-if="!embedded">Реестр рисков</h1>
      <h2 v-else>Риски проекта</h2>
    </div>
    <div v-if="auth.manager" class="toolbar">
      <button @click="create">＋ Добавить вручную</button
      ><button class="primary" :disabled="busy" @click="scan">
        {{ busy ? "Анализ…" : "Повторный анализ" }}</button
      ><button
        v-for="ext in ['xlsx', 'pdf']"
        :key="ext"
        @click="
          ui.act(
            () =>
              download(
                '/risks/export.' + ext + '?' + query(),
                'Реестр рисков.' + ext,
              ),
            '',
          )
        "
      >
        {{ ext.toUpperCase() }}
      </button>
    </div>
  </div>
  <details class="filter-box" open>
    <summary>Фильтры</summary>
    <div class="filters risk-registry-filters">
      <label class="risk-object-filter">Объект<input v-model="filters.object_search" placeholder="Найти проект или сотрудника" type="search" @input="scheduleFilters" aria-label="Поиск по объекту риска" /></label>
      <label>Тип риска<SearchSelect v-model="filters.risk_type_id" :options="[{value:'',label:'Все типы'}, ...types.map(t => ({value:t.risk_type_id,label:t.name}))]" @change="ui.act(applyFilters, '')" aria-label="Тип риска" /></label><SearchSelect
        v-model="filters.status"
        @change="ui.act(applyFilters, '')"
        aria-label="Статус риска"
       :options="[{value:'',label:'Все статусы'}, ...Object.entries(riskStatuses).map(([value,label]) => ({value,label}))]" /><SearchSelect
        v-model="filters.severity"
        @change="ui.act(applyFilters, '')"
        aria-label="Критичность"
       :options="[{value:'',label:'Любая критичность'}, ...Object.entries(severities).map(([value,label]) => ({value,label}))]" /><label
        >Выявлены с<input
          type="date"
          v-model="filters.from"
          @change="ui.act(applyFilters, '')" /></label
      ><label
        >Выявлены по<input
          type="date"
          v-model="filters.to"
          @change="ui.act(applyFilters, '')" /></label
      ><label class="check"
        ><input
          type="checkbox"
          v-model="filters.unviewed"
          @change="ui.act(applyFilters, '')"
        />Непросмотренные</label
      >
      <button @click="ui.act(resetFilters, '')">Сбросить</button>
    </div>
  </details>
  <div class="grid stats">
    <div class="stat">
      <span>По выбранным фильтрам</span><strong>{{ items.length }}</strong>
    </div>
    <div class="stat">
      <span>Открытые</span><strong>{{ active.length }}</strong>
    </div>
    <div class="stat">
      <span>Критические</span
      ><strong>{{
        active.filter((r) => r.severity === "critical").length
      }}</strong>
    </div>
    <div class="stat">
      <span>Основание устранено</span
      ><strong>{{ active.filter((r) => r.is_cause_resolved).length }}</strong>
    </div>
  </div>
  <div class="table-wrap mobile-cards">
    <table>
      <thead>
        <tr>
          <th>Тип риска</th>
          <th>Объект</th>
          <th>Критичность</th>
          <th>Показатель</th>
          <th>Выявлен</th>
          <th>Статус</th>
          <th>Ответственный</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="r in items"
          :key="r.risk_id"
          :class="{
            'risk-row': !['closed', 'rejected'].includes(r.status),
            ['risk-' + r.severity]: !['closed', 'rejected'].includes(r.status),
          }"
        >
          <td>
            <RouterLink
              :to="{
                path: '/risks/' + r.risk_id,
                query: { returnTo: returnUrl },
              }"
              ><strong>{{ r.type_name }}</strong></RouterLink
            ><small v-if="!r.is_viewed" style="display: block"
              >Не просмотрен</small
            ><small v-if="r.is_cause_resolved" style="display: block"
              >Основание устранено</small
            >
          </td>
          <td data-label="Объект">
            <RouterLink
              v-if="riskObjectLocation(r, auth.manager, projectId)"
              :to="riskObjectLocation(r, auth.manager, projectId)"
              >{{
                r.task_name || r.subject_name || r.project_name
              }}</RouterLink><span v-else>{{
              r.subject_name || r.project_name || "Сотрудник"
            }}</span
            ><span
              v-if="r.task_name || r.subject_name"
              class="object-project"
              >{{ r.project_name }}</span
            >
          </td>
          <td data-label="Критичность">
            <span class="badge" :class="r.severity">{{
              severities[r.severity]
            }}</span>
          </td>
          <td data-label="Показатель">{{ number(r.measured_value, 2) }}</td>
          <td data-label="Выявлен">{{ date(r.detected_at) }}</td>
          <td data-label="Статус">
            <span class="badge" :class="r.status">{{
              riskStatuses[r.status]
            }}</span>
          </td>
          <td data-label="Ответственный">
            {{ r.responsible_name || "Не назначен" }}
          </td>
        </tr>
      </tbody>
    </table>
    <p v-if="!items.length" class="empty">
      Риски по выбранным фильтрам не найдены
    </p>
  </div>
  <Modal v-if="show" title="Добавление риска вручную" @close="show = false"
    ><form @submit.prevent="save">
      <label
        >Тип риска<SearchSelect v-model="form.risk_type_id" required :options="types.map(t => ({value:t.risk_type_id,label:t.name}))" /></label
      ><label
        >Проект<SearchSelect
          v-model="form.project_id"
          :disabled="Boolean(projectId)"
          @change="ui.act(loadTasks, '')"
          required
         :options="projects.filter(p => !projectId || p.project_id === projectId).map(p => ({value:p.project_id,label:p.name}))" /></label
      ><label
        >Задача, необязательно<SearchSelect v-model="form.task_id" :options="[{value:null,label:'Без привязки к задаче'}, ...tasks.map(t => ({value:t.task_id,label:taskLabel(t,tasks)}))]" /></label
      ><label
        >Критичность<SearchSelect v-model="form.severity" :options="Object.entries(severities).map(([value,label]) => ({value,label}))" /></label
      ><label>Обоснование<textarea v-model="form.description" required /></label
      ><button class="primary">Добавить риск</button>
    </form></Modal
  >
</template>
<style scoped>
.filter-box {
  container: risk-filters / inline-size;
}
.risk-registry-filters {
  display: grid;
  grid-template-columns: minmax(0, 1.3fr) minmax(0, 1.2fr) repeat(2, minmax(0, 1fr));
  gap: 12px;
  align-items: end;
  max-width: 100%;
}
.risk-registry-filters > * {
  min-width: 0;
  width: 100%;
  max-width: 100%;
}
.risk-registry-filters .check {
  display: grid;
  grid-template-columns: 16px minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  min-height: 40px;
  padding: 8px 0;
  white-space: normal;
  overflow-wrap: anywhere;
  font-size: 12px;
  line-height: 20px;
}
.risk-registry-filters .check input {
  width: 16px;
  min-height: 16px;
  margin: 0;
}
.risk-registry-filters > button {
  padding-inline: 12px;
}
.risk-registry-filters :deep(input) {
  min-width: 0;
  max-width: 100%;
  font-size: 13px;
  text-overflow: ellipsis;
}
.risk-registry-filters :deep(input[aria-expanded="true"]) {
  text-overflow: clip;
}
@container risk-filters (min-width: 1420px) {
  .risk-registry-filters {
    grid-template-columns: minmax(230px, 1.4fr) minmax(196px, 1.2fr) minmax(148px, 1fr) minmax(176px, 1fr) 150px 150px 144px 88px;
  }
}
@container risk-filters (max-width: 850px) {
  .risk-registry-filters {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@container risk-filters (max-width: 420px) {
  .risk-registry-filters {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
