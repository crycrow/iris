<script setup>
import { ref, onMounted, computed } from "vue";
import { useRoute } from "vue-router";
import { api } from "../../../common/api/client.js";
import { useUi } from "../../../common/stores/ui.js";
import { useAuth } from "../../../common/stores/auth.js";
import {
  today,
  monday,
  shiftDate,
  date,
  number,
  list,
} from "../../../common/utils/format.js";
import Modal from "../../../common/components/Modal.vue";
import SearchSelect from "../../../common/components/SearchSelect.vue";
import TimeEntryGroups from "./TimeEntryGroups.vue";
const auth = useAuth();
const route = useRoute();
const dateParam = (value, fallback) => typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(Date.parse(value)) ? value : fallback;
const ui = useUi(),
  groups = ref([]),
  entries = ref([]),
  employees = ref([]),
  projects = ref([]),
  selectedUser = ref(""),
  selectedProject = ref(""),
  selected = ref(""),
  periodFrom = ref(dateParam(route.query.from, monday(today()))),
  periodTo = ref(dateParam(route.query.to, shiftDate(monday(today()), 6))),
  form = ref({ task_id: "", work_date: today(), hours: 8, comment: "" }),
  editing = ref(null),
  busy = ref(false);
const tasks = computed(() =>
  groups.value.flatMap((p) =>
    p.tasks.map((t) => ({ ...t, project_name: p.project_name })),
  ),
);
const taskOptions = computed(() => tasks.value.map((task) => ({
  value: task.task_id,
  label: '　'.repeat(task.task_depth || 0) + task.name + ' · ' + task.project_name,
})));
const employeeOptions = computed(() => [
  { value: "", label: "Все сотрудники" },
  ...employees.value.slice().sort((a, b) => a.full_name.localeCompare(b.full_name, "ru"))
    .map((person) => ({ value: person.user_id, label: person.full_name })),
]);
const projectOptions = computed(() => [
  { value: "", label: "Все проекты" },
  ...projects.value.slice().sort((a, b) => a.name.localeCompare(b.name, "ru"))
    .map((project) => ({ value: project.project_id, label: project.name })),
]);
const filteredEntries = computed(() => entries.value.filter((entry) =>
  (!selectedUser.value || String(entry.user_id) === String(selectedUser.value)) &&
  (!selectedProject.value || String(entry.project_id) === String(selectedProject.value)),
));
const days = computed(() => {
  const count =
    Math.floor(
      (new Date(periodTo.value + "T12:00:00") -
        new Date(periodFrom.value + "T12:00:00")) /
        86400000,
    ) + 1;
  if (!Number.isFinite(count) || count < 1 || count > 35) return [];
  return Array.from({ length: count }, (_, i) => {
    const d = shiftDate(periodFrom.value, i);
    return {
      date: d,
      hours: filteredEntries.value
        .filter((e) => e.work_date === d)
        .reduce((sum, e) => sum + Number(e.hours), 0),
    };
  });
});
const daily = computed(() =>
  filteredEntries.value
    .filter((e) => !selected.value || e.work_date === selected.value)
    .slice()
    .sort((a, b) => b.work_date.localeCompare(a.work_date)),
);
const total = computed(() =>
  daily.value.reduce((sum, e) => sum + Number(e.hours), 0),
);
let loadVersion = 0;
async function load() {
  if (!periodFrom.value || !periodTo.value || periodFrom.value > periodTo.value)
    throw new Error("Проверьте начало и окончание периода");
  const params = new URLSearchParams({
    from: periodFrom.value,
    to: periodTo.value,
  });
  if (!auth.admin) params.set("user_id", auth.user.user_id);
  const version = ++loadVersion;
  const loaded = list(await api.get(`/time-entries?${params}`));
  if (version === loadVersion) entries.value = loaded;
}
async function setPeriod(kind) {
  selected.value = "";
  const now = today(),
    monthStart = now.slice(0, 8) + "01";
  if (kind === "week") {
    periodFrom.value = monday(now);
    periodTo.value = shiftDate(periodFrom.value, 6);
  }
  if (kind === "month") {
    periodFrom.value = monthStart;
    periodTo.value = now;
  }
  if (kind === "previous") {
    const current = new Date(monthStart + "T12:00:00");
    current.setMonth(current.getMonth() - 1);
    periodFrom.value = `${current.getFullYear()}-${String(current.getMonth() + 1).padStart(2, "0")}-01`;
    periodTo.value = shiftDate(monthStart, -1);
  }
  if (kind === "quarter") {
    const month = Math.floor((Number(now.slice(5, 7)) - 1) / 3) * 3 + 1;
    periodFrom.value = `${now.slice(0, 4)}-${String(month).padStart(2, "0")}-01`;
    periodTo.value = now;
  }
  await ui.act(load, "");
}
async function applyPeriod() {
  selected.value = "";
  await ui.act(load, "");
}
onMounted(() =>
  ui.act(async () => {
    const [entryTasks, people, availableProjects] = await Promise.all([
      api.get("/my/entry-tasks"),
      auth.admin ? api.get("/users") : Promise.resolve([]),
      auth.admin ? api.get("/projects") : Promise.resolve([]),
    ]);
    groups.value = list(entryTasks);
    employees.value = list(people);
    projects.value = list(availableProjects);
    if (tasks.value.length) form.value.task_id = tasks.value[0].task_id;
    await load();
  }, ""),
);
async function resetFilters() {
  selectedUser.value = "";
  selectedProject.value = "";
  await setPeriod("week");
}
async function save() {
  busy.value = true;
  await ui.act(async () => {
    await api.post("/time-entries", form.value);
    selected.value = form.value.work_date;
    if (selected.value < periodFrom.value || selected.value > periodTo.value) {
      periodFrom.value = monday(selected.value);
      periodTo.value = shiftDate(periodFrom.value, 6);
    }
    await load();
    form.value.comment = "";
  }, "Трудозатраты внесены");
  busy.value = false;
}
async function navigate(n) {
  periodFrom.value = shiftDate(monday(periodFrom.value), n * 7);
  periodTo.value = shiftDate(periodFrom.value, 6);
  selected.value = "";
  await ui.act(load, "");
}
async function update() {
  await ui.act(async () => {
    const { task_id, work_date, hours, comment } = editing.value;
    await api.put("/time-entries/" + editing.value.entry_id, {
      task_id,
      work_date,
      hours,
      comment,
    });
    editing.value = null;
    await load();
  });
}
async function remove(e) {
  if (!window.confirm("Удалить запись о трудозатратах?")) return;
  await ui.act(async () => {
    await api.del("/time-entries/" + e.entry_id);
    await load();
  }, "Запись удалена");
}
</script>
<template>
  <div class="page-head">
    <div>
      <h1>{{ auth.admin ? "Табель сотрудников" : "Мои трудозатраты" }}</h1>
      <p v-if="auth.admin">Списания всех сотрудников за выбранный период</p>
    </div>
  </div>
  <section class="card">
    <h2>{{ auth.admin ? "Внести свои трудозатраты" : "Внести трудозатраты" }}</h2>
    <form v-if="tasks.length" @submit.prevent="save">
      <div class="form-grid">
        <label
          >Задача<SearchSelect v-model="form.task_id" :options="taskOptions" placeholder="Выберите задачу" aria-label="Задача" required /></label
        ><label
          >Дата<input
            type="date"
            v-model="form.work_date"
            :max="today()"
            required /></label
        ><label
          >Часы<input
            type="number"
            min=".5"
            max="24"
            step=".5"
            v-model.number="form.hours"
            required /></label
        ><label
          >Комментарий, необязательно<input v-model="form.comment"
        /></label>
      </div>
      <div><button class="primary" :disabled="busy">Сохранить</button></div>
    </form>
    <p v-else class="empty">Нет назначенных задач, доступных для списания</p>
  </section>
  <form class="card period-filter" @submit.prevent="applyPeriod">
    <div v-if="auth.admin" class="timesheet-people-filters">
      <label>Сотрудник<SearchSelect v-model="selectedUser" :options="employeeOptions" placeholder="Все сотрудники" aria-label="Сотрудник" /></label>
      <label>Проект<SearchSelect v-model="selectedProject" :options="projectOptions" placeholder="Все проекты" aria-label="Проект" /></label>
    </div>
    <div class="filters">
      <label
        >С даты<input
          v-model="periodFrom"
          type="date"
          :max="periodTo"
          required /></label
      ><label
        >По дату<input
          v-model="periodTo"
          type="date"
          :min="periodFrom"
          required /></label
      ><button class="primary">Показать</button>
    </div>
    <div class="toolbar">
      <button type="button" @click="setPeriod('week')">Текущая неделя</button
      ><button type="button" @click="setPeriod('month')">Текущий месяц</button
      ><button type="button" @click="setPeriod('previous')">
        Прошлый месяц</button
      ><button type="button" @click="setPeriod('quarter')">
        Текущий квартал
      </button><button type="button" @click="resetFilters">Сбросить фильтры</button>
    </div>
  </form>
  <section class="card">
    <div class="page-head">
      <h2>Табель за период</h2>
      <div class="toolbar">
        <button @click="navigate(-1)" aria-label="Предыдущая неделя">←</button
        ><span>{{ date(periodFrom) }} по {{ date(periodTo) }}</span
        ><button
          @click="navigate(1)"
          :disabled="periodFrom >= monday(today())"
          aria-label="Следующая неделя"
        >
          →
        </button>
      </div>
    </div>
    <div v-if="days.length" class="week-grid">
      <button
        v-for="(day, i) in days"
        :key="day.date"
        class="day"
        :class="{
          selected: selected === day.date,
          filled: day.hours > 0,
          overtime: !auth.admin && day.hours > 8,
        }"
        @click="selected = day.date"
        :aria-label="date(day.date) + ' ' + number(day.hours) + ' часов'"
      >
        <small>{{
          ["Вс", "Пн", "Вт", "Ср", "Чт", "Пт", "Сб"][
            new Date(day.date + "T12:00:00").getDay()
          ]
        }}</small>{{ day.date.slice(8) }}.{{ day.date.slice(5, 7)
        }}<strong>{{ number(day.hours) }} ч</strong>
        <small v-if="!auth.admin && day.hours > 8" class="overtime-label">Сверх 8 ч</small>
      </button>
    </div>
    <p v-if="!auth.admin && days.some((day) => day.hours > 8)" class="overtime-note">
      Выделены дни со списаниями более 8 часов.
    </p>
    <div class="page-head">
      <h3>
        {{ selected ? "Записи за " + date(selected) : "Все записи за период" }}
      </h3>
      <div class="toolbar">
        <span class="timesheet-total">{{ selected ? 'За день' : 'За период' }} <strong>{{ number(total) }} ч</strong></span>
        <button v-if="selected" @click="selected = ''">Все даты</button>
      </div>
    </div>
    <TimeEntryGroups v-if="auth.admin && daily.length" :entries="daily" :current-user-id="auth.user.user_id" @edit="editing = { ...$event }" @remove="remove" />
    <div v-else-if="daily.length" class="table-wrap mobile-cards">
      <table>
        <thead>
          <tr>
            <th>Дата</th>
            <th v-if="auth.admin">Сотрудник</th>
            <th>Задача</th>
            <th>Часы</th>
            <th>Комментарий</th>
            <th />
          </tr>
        </thead>
        <tbody>
          <tr v-for="e in daily" :key="e.entry_id">
            <td data-label="Дата">{{ date(e.work_date) }}</td>
            <td v-if="auth.admin" data-label="Сотрудник">{{ e.user_name }}</td>
            <td>
              <strong>{{
                e.task_name || tasks.find((t) => t.task_id === e.task_id)?.name
              }}</strong><small style="display: block">{{
                e.project_name
              }}</small>
            </td>
            <td data-label="Часы">{{ number(e.hours) }}</td>
            <td data-label="Комментарий">{{ e.comment }}</td>
            <td>
              <div v-if="e.user_id === auth.user.user_id" class="toolbar">
                <button @click="editing = { ...e }">Изменить</button
                ><button class="danger" @click="remove(e)">Удалить</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-else class="empty">За выбранные даты списаний нет</p>
  </section>
  <Modal
    v-if="editing"
    title="Редактирование трудозатрат"
    @close="editing = null"
    ><form @submit.prevent="update">
      <label
        >Дата<input
          v-model="editing.work_date"
          type="date"
          :max="today()"
          required /></label
      ><label
        >Часы<input
          v-model.number="editing.hours"
          type="number"
          min=".5"
          max="24"
          step=".5"
          required /></label
      ><label>Комментарий<input v-model="editing.comment" /></label
      ><button class="primary">Сохранить</button>
    </form></Modal
  >
</template>
<style scoped>
.timesheet-people-filters { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.timesheet-total { color: var(--secondary); white-space: nowrap; }
.timesheet-total strong { color: var(--text); font-variant-numeric: tabular-nums; margin-left: 8px; }
@media (max-width: 640px) { .timesheet-people-filters { grid-template-columns: 1fr; gap: 0; } }
</style>
