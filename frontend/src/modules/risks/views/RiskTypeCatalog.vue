<script setup>
import SearchSelect from "../../../common/components/SearchSelect.vue";
import { ref, onMounted, computed } from "vue";
import { api } from "../../../common/api/client.js";
import { useAuth } from "../../../common/stores/auth.js";
import { useUi } from "../../../common/stores/ui.js";
import { list, severities, number } from "../../../common/utils/format.js";
import Modal from "../../../common/components/Modal.vue";
const auth = useAuth(),
  ui = useUi(),
  types = ref([]),
  options = ref({ objects: {}, metrics: {} }),
  form = ref(null),
  groupSelection = ref(""),
  q = ref("");
async function load() {
  const result = await api.get("/risk-types");
  types.value = list(result);
  options.value = result.custom_options || { objects: {}, metrics: {} };
}
onMounted(() => ui.act(load, ""));
const groups = computed(() => [
  ...new Set(types.value.map((t) => t.risk_group).filter(Boolean)),
]);
const metricNames = {
  delta_t: "Просрочка в рабочих днях",
  t_safe: "Рабочие дни без списаний",
  u_plan: "Плановая загрузка, %",
  u_fact: "Фактическая загрузка, %",
  s: "Прогноз сдвига срока, дн.",
  deviation_share: "Доля задач с перерасходом, %",
  spi: "Выполнение плана по срокам",
  cpi: "Эффективность трудозатрат",
  w: "Остаток работ, ч",
  m: "Доступная мощность, ч",
  k: "Доля работ участника, %",
  imbalance: "Несбалансированная загрузка команды",
  capacity_gap: "Дефицит доступных часов",
  concentration: "Доля работ участника, %",
};
const operators = {
  gt: "Больше",
  gte: "Больше или равно",
  lt: "Меньше",
  lte: "Меньше или равно",
};
const paramLabels = {
  consecutive_weeks: "Последовательных недель для подтверждения",
  days_high: "Высокая критичность с указанного дня",
  days_critical: "Критическая степень с указанного дня",
  cpi_threshold: "Порог эффективности трудозатрат",
  history_days: "Период истории, дней",
  fact_weeks: "Недель фактической перегрузки подряд",
  load_high: "Высокая загрузка, %",
  load_critical: "Критическая загрузка, %",
  team_min: "Минимальное число участников команды",
  h_min: "Существенность, ч",
  p_min: "Минимальная доля освоенного объёма",
  k: "Число недель подряд",
  t_safe: "Рабочих дней без списаний",
  n_min: "Минимальное число задач",
  N_min: "Минимальное число задач",
  gamma: "Доля задач с отклонениями",
  theta: "Допустимое отклонение индекса",
  underload_threshold: "Порог недостаточной загрузки",
  overload_threshold: "Порог перегрузки",
};
async function save() {
  await ui.act(async () => {
    const keys = [
      "name",
      "description",
      "risk_group",
      "metric",
      "condition_op",
      "threshold",
      "severity",
      "recommendation",
      "is_active",
      "params",
    ];
    if (form.value.object_kind) keys.push("object_kind");
    const payload = Object.fromEntries(
      keys.map((key) => [key, form.value[key]]),
    );
    if (form.value.risk_type_id)
      await api.put("/risk-types/" + form.value.risk_type_id, payload);
    else await api.post("/risk-types", payload);
    form.value = null;
    await load();
  });
}
const filtered = computed(() =>
  types.value.filter((t) =>
    [t.name, t.risk_group, t.description]
      .join(" ")
      .toLowerCase()
      .includes(q.value.toLowerCase()),
  ),
);
function newType() {
  groupSelection.value = groups.value.includes("Сроки")
    ? "Сроки"
    : groups.value[0] || "__new_group__";
  form.value = {
    name: "",
    description: "",
    risk_group:
      groupSelection.value === "__new_group__" ? "" : groupSelection.value,
    object_kind: "task",
    metric: "progress_pct",
    condition_op: "lt",
    threshold: 50,
    severity: "medium",
    recommendation: "",
    is_active: true,
    params: { consecutive_weeks: 1 },
  };
}
function editType(type) {
  groupSelection.value = type.risk_group;
  form.value = { ...type, params: { ...type.params } };
}
function chooseGroup() {
  form.value.risk_group =
    groupSelection.value === "__new_group__" ? "" : groupSelection.value;
}
function chooseObject() {
  const metrics = options.value.metrics[form.value.object_kind] || [];
  if (!metrics.some((metric) => metric.key === form.value.metric))
    form.value.metric = metrics[0]?.key || "";
}
function metricLabel(key) {
  const item = Object.values(options.value.metrics)
    .flat()
    .find((metric) => metric.key === key);
  return metricNames[key] || (item ? `${item.name}, ${item.unit}` : "Другой показатель");
}
const availableMetrics = computed(() => {
  if (!form.value) return {};
  if (form.value.object_kind)
    return Object.fromEntries(
      (options.value.metrics[form.value.object_kind] || []).map((metric) => [
        metric.key,
        `${metric.name}, ${metric.unit}`,
      ]),
    );
  const code = form.value.code?.startsWith("custom:")
    ? form.value.code.split(":")[1]
    : form.value.code;
  const keys = code === "overload" ? ["u_plan", "u_fact"] : [form.value.metric];
  return Object.fromEntries(keys.map((k) => [k, metricLabel(k)]));
});
</script>
<template>
  <div class="page-head">
    <h1>Справочник рисков</h1>
    <button v-if="auth.admin" class="primary" @click="newType">
      Добавить тип риска
    </button>
  </div>
  <div class="filters">
    <input
      v-model="q"
      placeholder="Поиск по типу или группе"
      aria-label="Поиск типа риска"
    />
  </div>
  <div class="table-wrap">
    <table class="catalog-table">
      <thead>
        <tr>
          <th>Тип риска</th>
          <th>Группа</th>
          <th>Условие выявления</th>
          <th>Рекомендация</th>
          <th>Состояние</th>
          <th v-if="auth.admin">Действия</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="t in filtered" :key="t.risk_type_id">
          <td>
            <strong>{{ t.name }}</strong>
            <div v-if="t.description && t.description !== t.name">
              {{ t.description }}
            </div>
          </td>
          <td>{{ t.risk_group }}</td>
          <td>
            <div v-if="t.object_kind">{{ options.objects[t.object_kind] }}</div>
            {{ metricLabel(t.metric) }}<br />{{ operators[t.condition_op] }}
            {{ number(t.threshold, 3) }}
            <div v-if="t.object_kind">
              {{
                Number(t.params.consecutive_weeks) === 1
                  ? "Одно недельное подтверждение"
                  : `Подтверждается ${number(t.params.consecutive_weeks, 0)} нед. подряд`
              }}
            </div>
          </td>
          <td>{{ t.recommendation }}</td>
          <td>
            <span class="badge">{{
              t.is_active ? "Активен" : "Выключен"
            }}</span>
          </td>
          <td v-if="auth.admin">
            <button @click="editType(t)">Изменить</button>
          </td>
        </tr>
        <tr v-if="!filtered.length">
          <td :colspan="auth.admin ? 6 : 5" class="empty">
            Типы рисков не найдены
          </td>
        </tr>
      </tbody>
    </table>
  </div>
  <Modal
    v-if="form"
    :title="form.risk_type_id ? 'Настройка типа риска' : 'Новый тип риска'"
    @close="form = null"
    ><form @submit.prevent="save">
      <label>Название<input v-model="form.name" required /></label
      ><label>Описание<textarea v-model="form.description" /></label>
      <div class="form-grid">
        <label
          >Группа<SearchSelect
            v-model="groupSelection"
            aria-label="Группа"
            @change="chooseGroup"
            required
           :options="[...groups.map(group => ({value:group,label:group})), {value:'__new_group__',label:'Добавить новую группу'}]" /></label
        >
        <label v-if="form.object_kind"
          >Объект проверки<SearchSelect
            v-model="form.object_kind"
            @change="chooseObject"
           :options="Object.entries(options.objects).map(([value,label]) => ({value,label}))" /></label
        >
      </div>
      <label v-if="groupSelection === '__new_group__'"
        >Название новой группы<input
          v-model.trim="form.risk_group"
          maxlength="100"
          required
      /></label>
      <label
        >Показатель<SearchSelect v-model="form.metric" :options="Object.entries(availableMetrics).map(([value,label]) => ({value,label}))" /></label
      >
      <div class="form-grid">
        <label
          >Условие<SearchSelect v-model="form.condition_op" :options="Object.entries(operators).map(([value,label]) => ({value,label}))" /></label
        ><label
          >Порог<input
            v-model.number="form.threshold"
            type="number"
            step="any"
            required /></label
        ><label
          >Базовая критичность<SearchSelect v-model="form.severity" :options="Object.entries(severities).map(([value,label]) => ({value,label}))" /></label
        >
      </div>
      <h3 v-if="Object.keys(form.params).length">Подтверждение условия</h3>
      <div class="form-grid">
        <label v-for="(_, key) in form.params" :key="key"
          >{{ paramLabels[key] || "Дополнительный параметр"
          }}<input
            v-model.number="form.params[key]"
            type="number"
            :step="key === 'consecutive_weeks' ? 1 : 'any'"
            :min="key === 'consecutive_weeks' ? 1 : undefined"
            :max="key === 'consecutive_weeks' ? 52 : undefined"
            required
        /></label>
      </div>
      <label
        >Рекомендация<textarea v-model="form.recommendation" required /></label
      ><label class="check"
        ><input type="checkbox" v-model="form.is_active" />Тип риска
        активен</label
      ><button class="primary">
        {{ form.risk_type_id ? "Сохранить настройки" : "Создать тип риска" }}
      </button>
    </form></Modal
  >
</template>

<style scoped>
.catalog-table {
  min-width: 850px;
}
.catalog-table th,
.catalog-table td {
  text-align: left;
  vertical-align: top;
}
.catalog-table td:first-child {
  min-width: 210px;
}
.catalog-table td:nth-child(3),
.catalog-table td:nth-child(4) {
  min-width: 190px;
}
.catalog-table td div {
  margin-top: 8px;
}
</style>
