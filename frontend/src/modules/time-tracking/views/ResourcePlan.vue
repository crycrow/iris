<script setup>
import { taskHierarchy, taskDepth, taskLabel } from "../taskFilters.js";
import SearchSelect from "../../../common/components/SearchSelect.vue";
import { ref, onMounted, computed, nextTick, watch } from "vue";
import { api, download } from "../../../common/api/client.js";
import { useUi } from "../../../common/stores/ui.js";
import { useAuth } from "../../../common/stores/auth.js";
import {
  number,
  today,
  list,
  taskStatuses,
} from "../../../common/utils/format.js";
import RiskBadge from "../../../common/components/RiskBadge.vue";
import Modal from "../../../common/components/Modal.vue";

const props = defineProps({
  projectId: Number,
  indicators: Object,
  taskIndicators: Object,
  focusUser: Number,
});
const emit = defineEmits(["saved"]);
const ui = useUi(),
  auth = useAuth();
const data = ref({ months: [], rows: [] }),
  tasks = ref([]);
const from = ref(""),
  to = ref(""),
  selectedUserId = ref(null);
const selectedMonth = ref(today().slice(0, 7));
const editing = ref(false),
  saving = ref(false),
  draft = ref([]);
const pickerOpen = ref(false),
  pickerMode = ref("add"),
  search = ref(""),
  selectedTasks = ref([]),
  candidateTaskId = ref(""),
  distributionTotal = ref("");
const currentMonth = today().slice(0, 7);
const months = computed(() =>
  data.value.months.filter(
    (month) =>
      (!from.value || month >= from.value) && (!to.value || month <= to.value),
  ),
);
const selectedUser = computed(() =>
  data.value.rows.find((row) => row.user_id === selectedUserId.value),
);
const canEdit = computed(
  () =>
    auth.manager &&
    selectedUser.value?.is_member !== false &&
    !selectedUser.value?.is_blocked &&
    (auth.admin || selectedMonth.value >= currentMonth),
);
const parentIds = computed(
  () => new Set(tasks.value.map((task) => task.parent_task_id).filter(Boolean)),
);
const totalPlan = computed(() =>
  data.value.rows.reduce(
    (sum, row) =>
      sum +
      months.value.reduce(
        (total, month) => total + Number(cell(row, month).plan),
        0,
      ),
    0,
  ),
);
const totalFact = computed(() =>
  data.value.rows.reduce(
    (sum, row) =>
      sum +
      months.value.reduce(
        (total, month) => total + Number(cell(row, month).fact),
        0,
      ),
    0,
  ),
);
const monthPlan = computed(() =>
  draft.value.reduce(
    (sum, row) =>
      sum + (row.has_plan && !row.removed ? Number(row.planned_hours || 0) : 0),
    0,
  ),
);
const monthFact = computed(() =>
  draft.value.reduce((sum, row) => sum + Number(row.fact || 0), 0),
);
const changes = computed(() =>
  draft.value.filter((row) =>
    row.removed
      ? row.original_plan
      : row.has_plan &&
        (!row.original_plan ||
          Number(row.planned_hours) !== row.original_hours),
  ),
);
const validHours = computed(() =>
  draft.value.every(
    (row) =>
      !row.has_plan ||
      row.removed ||
      (row.planned_hours !== "" &&
        row.planned_hours !== null &&
        Number.isFinite(Number(row.planned_hours)) &&
        Number(row.planned_hours) >= 0 &&
        Number(row.planned_hours) <= 9999.99 &&
        Math.abs(
          Number(row.planned_hours) * 100 -
            Math.round(Number(row.planned_hours) * 100),
        ) < 0.00001),
  ),
);
const eligibleTasks = computed(() =>
  tasks.value.filter(
    (task) =>
      !task.is_milestone &&
      !parentIds.value.has(task.task_id) &&
      task.status !== "cancelled" &&
      task.start_date.slice(0, 7) <= selectedMonth.value &&
      task.due_date.slice(0, 7) >= selectedMonth.value,
  ),
);
const availableTasks = computed(() =>
  eligibleTasks.value.filter(
    (task) =>
      !draft.value.some(
        (row) => row.task_id === task.task_id && row.has_plan && !row.removed,
      ),
  ),
);
const matchingTasks = computed(() =>
  (pickerMode.value === "add"
    ? availableTasks.value
    : eligibleTasks.value
  ).filter(
    (task) =>
      !selectedTasks.value.includes(task.task_id) &&
      task.name
        .toLocaleLowerCase("ru")
        .includes(search.value.trim().toLocaleLowerCase("ru")),
  ),
);
const chosenTasks = computed(() =>
  selectedTasks.value
    .map((id) => eligibleTasks.value.find((task) => task.task_id === id))
    .filter(Boolean),
);
const distributionCents = computed(() => {
  if (distributionTotal.value === "" || distributionTotal.value === null)
    return null;
  const amount = Number(distributionTotal.value);
  const cents = Math.round(amount * 100);
  if (
    !Number.isFinite(amount) ||
    amount < 0 ||
    Math.abs(amount * 100 - cents) >= 0.00001 ||
    !chosenTasks.value.length ||
    cents > chosenTasks.value.length * 999999
  )
    return null;
  return cents;
});
const distributionPreview = computed(() => {
  const cents = distributionCents.value;
  if (cents === null) return [];
  return chosenTasks.value.map((task, index) => ({
    task_id: task.task_id,
    name: task.name,
    planned_hours:
      (Math.floor(cents / chosenTasks.value.length) +
        (index < cents % chosenTasks.value.length ? 1 : 0)) /
      100,
  }));
});
watch(search, () => {
  candidateTaskId.value = "";
});

function cell(row, month) {
  return (
    row.months?.find((item) => item.month === month) || {
      plan: 0,
      fact: 0,
      has_plan: false,
    }
  );
}
function monthLabel(month) {
  return new Date(`${month}-01T12:00:00`).toLocaleDateString("ru-RU", {
    month: "long",
    year: "numeric",
  });
}
function taskAllowsMonth(row) {
  return (
    row.status !== "cancelled" &&
    row.start_date.slice(0, 7) <= selectedMonth.value &&
    row.due_date.slice(0, 7) >= selectedMonth.value
  );
}
async function load() {
  const [resources, work] = await Promise.all([
    api.get(`/projects/${props.projectId}/resources`),
    api.get(`/projects/${props.projectId}/tasks`),
  ]);
  data.value = { ...resources, rows: [...(resources.rows || [])].sort((a, b) => a.full_name.localeCompare(b.full_name, "ru")) };
  tasks.value = taskHierarchy(list(work));
  await focusUser();
}
async function focusUser() {
  if (!props.focusUser) return;
  await nextTick();
  document
    .getElementById(`resource-user-${props.focusUser}`)
    ?.scrollIntoView({ block: "center", behavior: "smooth" });
}
watch(() => props.focusUser, focusUser);
onMounted(() => ui.act(load, ""));

function resetDraft() {
  draft.value = (selectedUser.value?.assignments || [])
    .filter(
      (row) =>
        cell(row, selectedMonth.value).has_plan ||
        Number(cell(row, selectedMonth.value).fact) > 0,
    )
    .map((row) => {
      const value = cell(row, selectedMonth.value);
      return {
        ...row,
        planned_hours: Number(value.plan),
        original_hours: Number(value.plan),
        has_plan: value.has_plan,
        original_plan: value.has_plan,
        fact: Number(value.fact),
        removed: false,
      };
    });
  pickerOpen.value = false;
  pickerMode.value = "add";
  selectedTasks.value = [];
  candidateTaskId.value = "";
  distributionTotal.value = "";
  search.value = "";
  editing.value = false;
}
function openAssignments(row) {
  selectedUserId.value = row.user_id;
  selectedMonth.value =
    from.value ||
    (data.value.months.includes(currentMonth)
      ? currentMonth
      : data.value.months.at(-1)) ||
    currentMonth;
  resetDraft();
}
function closeAssignments() {
  if (
    saving.value ||
    (changes.value.length &&
      !window.confirm("Отменить несохранённые изменения назначений?"))
  )
    return;
  selectedUserId.value = null;
  editing.value = false;
}
function changeMonth(event) {
  const month = event.target.value;
  if (
    !month ||
    (changes.value.length &&
      !window.confirm(
        "Отменить несохранённые изменения и открыть другой месяц?",
      ))
  ) {
    event.target.value = selectedMonth.value;
    return;
  }
  selectedMonth.value = month;
  resetDraft();
}
function removePlan(row) {
  if (!row.original_plan && !row.fact)
    draft.value = draft.value.filter((item) => item !== row);
  else row.removed = true;
}
function restorePlan(row) {
  row.removed = false;
}
function openPicker(mode) {
  pickerMode.value = mode;
  pickerOpen.value = true;
  selectedTasks.value = [];
  candidateTaskId.value = "";
  distributionTotal.value = "";
  search.value = "";
}
function selectTask() {
  const id = Number(candidateTaskId.value);
  if (matchingTasks.value.some((task) => task.task_id === id)) {
    selectedTasks.value.push(id);
  }
  candidateTaskId.value = "";
}
function unselectTask(taskId) {
  selectedTasks.value = selectedTasks.value.filter((id) => id !== taskId);
}
function ensureDraftTask(task) {
  let row = draft.value.find((item) => item.task_id === task.task_id);
  if (!row) {
    row = {
      task_id: task.task_id,
      task_name: task.name,
      start_date: task.start_date,
      due_date: task.due_date,
      status: task.status,
      planned_hours: 0,
      original_hours: 0,
      has_plan: true,
      original_plan: false,
      fact: 0,
      removed: false,
    };
    draft.value.push(row);
  }
  row.has_plan = true;
  row.removed = false;
  return row;
}
function closePicker() {
  selectedTasks.value = [];
  candidateTaskId.value = "";
  distributionTotal.value = "";
  pickerOpen.value = false;
  search.value = "";
}
function addTasks() {
  chosenTasks.value.forEach(ensureDraftTask);
  closePicker();
}
function distributeEqually() {
  if (distributionCents.value === null) return;
  distributionPreview.value.forEach((item) => {
    const task = chosenTasks.value.find(
      (candidate) => candidate.task_id === item.task_id,
    );
    ensureDraftTask(task).planned_hours = item.planned_hours;
  });
  closePicker();
}
async function save() {
  if (
    !canEdit.value ||
    !validHours.value ||
    !changes.value.length ||
    pickerOpen.value
  )
    return;
  saving.value = true;
  try {
    await api.put(`/projects/${props.projectId}/resources/month`, {
      user_id: selectedUserId.value,
      month: selectedMonth.value,
      items: changes.value
        .filter((row) => !row.removed)
        .map((row) => ({
          task_id: row.task_id,
          planned_hours: Number(row.planned_hours),
        })),
      remove_task_ids: changes.value
        .filter((row) => row.removed && row.original_plan)
        .map((row) => row.task_id),
    });
    await load();
    resetDraft();
    emit("saved");
    ui.notify("Назначения на месяц сохранены");
  } catch (error) {
    ui.notify(error.message, true);
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <div class="page-head">
    <h2>Ресурсный план</h2>
    <div class="toolbar">
      <button
        v-for="ext in ['xlsx', 'pdf']"
        :key="ext"
        @click="
          ui.act(
            () =>
              download(
                `/projects/${projectId}/export/resources.${ext}`,
                `Ресурсный план.${ext}`,
              ),
            '',
          )
        "
      >
        {{ ext.toUpperCase() }}
      </button>
    </div>
  </div>
  <div class="grid stats">
    <div class="stat">
      <span>Сотрудников</span><strong>{{ data.rows.length }}</strong>
    </div>
    <div class="stat">
      <span>План за период, ч</span><strong>{{ number(totalPlan, 2) }}</strong>
    </div>
    <div class="stat">
      <span>Факт за период, ч</span><strong>{{ number(totalFact, 2) }}</strong>
    </div>
  </div>
  <div class="filters">
    <label
      >С месяца<input v-model="from" type="month" :max="to || undefined"
    /></label>
    <label
      >По месяц<input v-model="to" type="month" :min="from || undefined"
    /></label>
    <button
      v-if="from || to"
      @click="
        from = '';
        to = '';
      "
    >
      Все месяцы
    </button>
  </div>
  <div class="table-wrap sticky-first resource-table">
    <table v-if="data.rows.length && months.length">
      <thead>
        <tr>
          <th>Сотрудник</th>
          <th v-for="month in months" :key="month" class="num">
            {{ month.slice(5) }}.{{ month.slice(0, 4)
            }}<span class="column-unit">План / факт, ч</span>
          </th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="row in data.rows"
          :key="row.user_id"
          :id="`resource-user-${row.user_id}`"
          :class="{
            'risk-row': indicators?.[row.user_id]?.length,
            'focused-object': focusUser === row.user_id,
          }"
        >
          <td>
            <div class="resource-person">
              <strong>{{ row.full_name }}</strong
              ><button class="small" @click="openAssignments(row)">
                Назначения
              </button>
            </div>
            <RiskBadge :risks="indicators?.[row.user_id] || []" />
          </td>
          <td v-for="month in months" :key="month" class="num">
            <strong>{{ number(cell(row, month).plan, 2) }}</strong
            ><span> / {{ number(cell(row, month).fact, 2) }}</span>
          </td>
        </tr>
      </tbody>
    </table>
    <p v-if="!data.rows.length" class="empty">
      Добавьте участников в обзор проекта
    </p>
    <p v-else-if="!months.length" class="empty">
      В выбранном периоде нет данных проекта
    </p>
  </div>

  <Modal
    v-if="selectedUser"
    :title="`Назначения · ${selectedUser.full_name}`"
    @close="closeAssignments"
  >
    <form class="month-assignments" @submit.prevent="save">
      <div class="assignment-toolbar">
        <label
          >Месяц<input
            type="month"
            :value="selectedMonth"
            :disabled="saving"
            required
            @change="changeMonth"
        /></label>
        <div class="month-totals">
          <span
            >План <strong>{{ number(monthPlan, 2) }} ч</strong></span
          ><span
            >Факт <strong>{{ number(monthFact, 2) }} ч</strong></span
          >
        </div>
        <button
          v-if="canEdit && !editing"
          type="button"
          class="primary"
          @click="editing = true"
        >
          Редактировать
        </button>
      </div>
      <p
        v-if="!auth.admin && selectedMonth < currentMonth"
        class="assignment-notice"
      >
        Прошедший месяц доступен для просмотра
      </p>
      <p v-else-if="selectedUser.is_blocked" class="assignment-notice">
        Учётная запись сотрудника заблокирована
      </p>
      <p v-else-if="selectedUser.is_member === false" class="assignment-notice">
        Сотрудник больше не входит в команду проекта
      </p>
      <div v-if="editing" class="toolbar assignment-actions">
        <button
          type="button"
          :disabled="saving"
          :aria-expanded="pickerOpen && pickerMode === 'add'"
          @click="openPicker('add')"
        >
          Добавить задачи
        </button>
        <button
          type="button"
          :disabled="saving || !eligibleTasks.length"
          :aria-expanded="pickerOpen && pickerMode === 'distribute'"
          @click="openPicker('distribute')"
        >
          Распределить часы
        </button>
      </div>
      <section
        v-if="pickerOpen && editing"
        class="task-picker"
        :aria-label="
          pickerMode === 'add' ? 'Добавление задач' : 'Распределение часов'
        "
      >
        <div class="task-selector">
          <label>
            Выбрать задачу
            <SearchSelect v-model="candidateTaskId" :disabled="saving || !matchingTasks.length" :options="matchingTasks.map(task => ({value:task.task_id,label:taskLabel(task,tasks)}))" :placeholder="matchingTasks.length ? 'Выберите задачу' : 'Нет подходящих задач'" @change="selectTask" />
          </label>
        </div>
        <ul
          v-if="chosenTasks.length"
          class="selected-tasks"
          aria-label="Выбранные задачи"
        >
          <li v-for="task in chosenTasks" :key="task.task_id">
            <span :style="{ paddingLeft: `${taskDepth(task, tasks) * 20}px` }">{{ task.name }}</span>
            <strong
              v-if="pickerMode === 'distribute' && distributionCents !== null"
            >
              {{
                number(
                  distributionPreview.find(
                    (item) => item.task_id === task.task_id,
                  ).planned_hours,
                  2,
                )
              }}
              ч
            </strong>
            <button
              type="button"
              class="small"
              :disabled="saving"
              :aria-label="`Убрать задачу «${task.name}» из выбора`"
              @click="unselectTask(task.task_id)"
            >
              ×
            </button>
          </li>
        </ul>
        <template v-if="pickerMode === 'distribute'">
          <label class="distribution-total">
            Всего часов для выбранных задач
            <input
              v-model.number="distributionTotal"
              type="number"
              min="0"
              :max="
                chosenTasks.length ? chosenTasks.length * 9999.99 : undefined
              "
              step="0.01"
              placeholder="Например, 40"
              :disabled="saving"
            />
          </label>
          <div
            v-if="distributionPreview.length"
            class="distribution-preview"
            aria-live="polite"
          >
            <div class="distribution-summary">
              <span>Итого по выбранным задачам</span>
              <strong>{{ number(distributionCents / 100, 2) }} ч</strong>
            </div>
          </div>
          <p class="distribution-note">
            Указанные часы заменят план выбранных задач за
            {{ monthLabel(selectedMonth) }}. Остальные задачи сохранят свои
            часы.
          </p>
        </template>
        <div class="toolbar">
          <button
            v-if="pickerMode === 'add'"
            type="button"
            class="primary"
            :disabled="saving || !chosenTasks.length"
            @click="addTasks"
          >
            Добавить выбранные ({{ chosenTasks.length }})
          </button>
          <button
            v-else
            type="button"
            class="primary"
            :disabled="saving || distributionCents === null"
            @click="distributeEqually"
          >
            Распределить
          </button>
          <button type="button" :disabled="saving" @click="closePicker">
            Отмена
          </button>
        </div>
      </section>
      <div v-if="draft.length" class="table-wrap assignment-details">
        <table>
          <thead>
            <tr>
              <th>Задача</th>
              <th class="num">План, ч</th>
              <th class="num">Факт, ч</th>
              <th v-if="editing"><span class="sr-only">Действия</span></th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in draft"
              :key="row.task_id"
              :class="{
                'removed-plan': row.removed,
                'risk-row': taskIndicators?.[row.task_id]?.length,
              }"
            >
              <td>
                <span :style="{ paddingLeft: `${taskDepth(tasks.find(t => t.task_id === row.task_id), tasks) * 20}px` }">{{ row.task_name }}</span
                ><span v-if="row.status === 'cancelled'" class="task-state">{{
                  taskStatuses[row.status]
                }}</span
                ><RiskBadge :risks="taskIndicators?.[row.task_id] || []" />
              </td>
              <td class="num" data-label="План, ч">
                <input
                  v-if="
                    editing &&
                    row.has_plan &&
                    !row.removed &&
                    taskAllowsMonth(row)
                  "
                  v-model.number="row.planned_hours"
                  type="number"
                  min="0"
                  max="9999.99"
                  step="0.01"
                  required
                  :disabled="saving"
                  :aria-label="`${row.task_name}, плановые часы за ${monthLabel(selectedMonth)}`"
                /><span v-else>{{
                  number(
                    row.has_plan && !row.removed ? row.planned_hours : 0,
                    2,
                  )
                }}</span>
              </td>
              <td class="num" data-label="Факт, ч">
                {{ number(row.fact, 2) }}
              </td>
              <td v-if="editing" class="assignment-row-actions">
                <button
                  v-if="row.removed"
                  type="button"
                  class="small"
                  :disabled="saving"
                  @click="restorePlan(row)"
                >
                  Вернуть план</button
                ><button
                  v-else-if="row.has_plan"
                  type="button"
                  class="small danger"
                  :disabled="saving"
                  :aria-label="`Удалить план задачи «${row.task_name}» только за ${monthLabel(selectedMonth)}`"
                  @click="removePlan(row)"
                >
                  Удалить план
                </button>
              </td>
            </tr>
          </tbody>
          <tfoot>
            <tr>
              <th>Итого за месяц</th>
              <th class="num">{{ number(monthPlan, 2) }}</th>
              <th class="num">{{ number(monthFact, 2) }}</th>
              <th v-if="editing"></th>
            </tr>
          </tfoot>
        </table>
      </div>
      <p v-else class="empty">На выбранный месяц нет назначений и списаний</p>
      <div class="assignment-footer">
        <template v-if="editing"
          ><button type="button" :disabled="saving" @click="resetDraft">
            Отменить изменения</button
          ><button
            class="primary"
            :disabled="saving || !changes.length || !validHours || pickerOpen"
          >
            {{ saving ? "Сохранение…" : "Сохранить назначения" }}
          </button></template
        >
        <button v-else type="button" @click="closeAssignments">Закрыть</button>
      </div>
    </form>
  </Modal>
</template>

<style scoped>
.resource-table table {
  min-width: 560px;
}
.resource-table th:first-child,
.resource-table td:first-child {
  min-width: 250px;
  max-width: 320px;
}
.resource-table td:not(:first-child) {
  min-width: 116px;
  white-space: nowrap;
}
.resource-person {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.resource-person strong {
  line-height: 1.4;
}
.resource-person button {
  flex-shrink: 0;
}
.column-unit {
  display: block;
  font-size: 14px;
  font-weight: 400;
  margin-top: 4px;
}
.month-assignments {
  display: grid;
  gap: 16px;
}
.assignment-toolbar {
  display: flex;
  gap: 16px;
  align-items: end;
  flex-wrap: wrap;
}
.assignment-toolbar > label {
  min-width: 170px;
  margin: 0;
}
.assignment-toolbar > button {
  margin-left: auto;
}
.month-totals {
  display: flex;
  gap: 24px;
  align-self: center;
  flex-wrap: wrap;
}
.month-totals span {
  display: grid;
  gap: 4px;
}
.month-totals strong {
  font-size: 18px;
}
.assignment-actions {
  margin: 0;
}
.assignment-notice {
  background: var(--inset);
  border-radius: 8px;
  padding: 12px 16px;
  margin: 0;
}
.task-picker {
  display: grid;
  gap: 12px;
  background: var(--inset);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
}
.task-picker > label {
  margin: 0;
}
.task-selector {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 12px;
}
.task-selector label {
  min-width: 0;
  margin: 0;
}
.task-selector select {
  width: 100%;
  text-overflow: ellipsis;
}
.selected-tasks {
  max-height: 230px;
  overflow-y: auto;
  display: grid;
  gap: 8px;
  padding: 0;
  margin: 0;
  list-style: none;
}
.selected-tasks li {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 8px;
  line-height: 1.4;
}
.selected-tasks li > span {
  flex: 1;
  min-width: 0;
}
.selected-tasks strong,
.selected-tasks button {
  flex-shrink: 0;
  white-space: nowrap;
}
.distribution-total {
  max-width: 300px;
  margin: 0;
}
.distribution-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.distribution-summary strong {
  white-space: nowrap;
}
.distribution-note {
  margin: 0;
  line-height: 1.5;
}
.assignment-details {
  max-height: 45vh;
}
.assignment-details table {
  min-width: 440px;
  width: 100%;
}
.assignment-details th,
.assignment-details td {
  padding: 12px;
}
.assignment-details td:first-child {
  min-width: 175px;
}
.assignment-details td.num,
.assignment-details th.num {
  width: 95px;
  min-width: 85px;
  white-space: nowrap;
}
.assignment-details input {
  width: 90px;
  text-align: right;
  padding: 8px;
}
.assignment-details tfoot {
  background: var(--inset);
}
.assignment-row-actions {
  width: 125px;
}
.assignment-row-actions button {
  white-space: nowrap;
}
.removed-plan td:first-child > span:first-child {
  text-decoration: line-through;
}
.task-state {
  display: block;
  margin-top: 4px;
}
.assignment-footer {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
}
@media (max-width: 600px) {
  .resource-person {
    align-items: flex-start;
    flex-direction: column;
    gap: 8px;
  }
  .resource-table th:first-child,
  .resource-table td:first-child {
    min-width: 180px;
  }
  .assignment-toolbar {
    align-items: center;
  }
  .assignment-toolbar > button {
    margin-left: 0;
  }
  .month-totals {
    gap: 16px;
  }
  .task-picker {
    padding: 12px;
  }
  .task-selector {
    grid-template-columns: 1fr;
  }
  .assignment-details {
    max-height: none;
  }
  .assignment-details table {
    min-width: 0;
  }
  .assignment-details thead {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
  }
  .assignment-details tbody {
    display: block;
  }
  .assignment-details tbody tr {
    display: grid;
    grid-template-columns: 1fr 1fr;
    border-bottom: 1px solid var(--border);
  }
  .assignment-details td {
    border-bottom: 0;
  }
  .assignment-details td:first-child {
    grid-column: 1 / -1;
    min-width: 0;
    padding-bottom: 8px;
  }
  .assignment-details td.num {
    width: auto;
    min-width: 0;
    display: flex;
    gap: 8px;
    justify-content: space-between;
    align-items: center;
    text-align: right;
  }
  .assignment-details td.num::before {
    content: attr(data-label);
    white-space: normal;
    text-align: left;
  }
  .assignment-details input {
    width: 74px;
  }
  .assignment-row-actions {
    grid-column: 1 / -1;
    width: auto;
    text-align: right;
    padding-top: 0;
  }
  .assignment-details tfoot {
    display: none;
  }
}
</style>
