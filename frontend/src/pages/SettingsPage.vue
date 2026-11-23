<script setup>
import { ref, onMounted } from "vue";
import { api } from "../common/api/client.js";
import { useUi } from "../common/stores/ui.js";
import { list } from "../common/utils/format.js";
import SearchSelect from "../common/components/SearchSelect.vue";
const ui = useUi(),
  items = ref([]);
const labels = {
  token_minutes: "Продолжительность сессии, минут",
  scheduler_day: "День еженедельного анализа",
  scheduler_time: "Время запуска по Москве",
};
const weekdays = {
  mon: "Понедельник",
  tue: "Вторник",
  wed: "Среда",
  thu: "Четверг",
  fri: "Пятница",
  sat: "Суббота",
  sun: "Воскресенье",
};
onMounted(() =>
  ui.act(async () => {
    items.value = list(await api.get("/settings")).filter(
      (item) => item.setting_key in labels,
    );
  }, ""),
);
async function save(item) {
  await ui.act(() =>
    api.put("/settings/" + item.setting_key, {
      setting_value: String(item.setting_value),
    }),
  );
}
</script>
<template>
  <div class="narrow">
    <div class="page-head"><h1>Настройки системы</h1></div>
    <form
      class="card setting-row"
      v-for="item in items"
      :key="item.setting_key"
      @submit.prevent="save(item)"
    >
      <label
        >{{ labels[item.setting_key] }}
        <SearchSelect
          v-if="item.setting_key === 'scheduler_day'"
          v-model="item.setting_value"
          :options="Object.entries(weekdays).map(([value, label]) => ({value, label}))"
          aria-label="День еженедельного анализа"
        />
        <input
          v-else-if="item.setting_key === 'scheduler_time'"
          v-model="item.setting_value"
          type="text"
          inputmode="numeric"
          placeholder="ЧЧ:ММ:СС"
          pattern="([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]"
          title="Время в формате ЧЧ:ММ:СС, например 23:55:00"
          maxlength="8"
          required
        />
        <input
          v-else
          v-model="item.setting_value"
          type="number"
          step="1"
          min="1"
          max="43200"
          required
        />
      </label>
      <button class="primary">Сохранить</button>
    </form>
  </div>
</template>
<style scoped>
.setting-row {
  display: flex;
  align-items: end;
  gap: 20px;
  margin-bottom: 16px;
}
.setting-row label {
  flex: 1;
  margin: 0;
}
@media (max-width: 520px) {
  .setting-row {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
