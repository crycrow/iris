<script setup>
import SearchSelect from "../common/components/SearchSelect.vue";
import { ref, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { api } from "../common/api/client.js";
import { useAuth } from "../common/stores/auth.js";
import { useUi } from "../common/stores/ui.js";
import {
  projectStatuses,
  date,
  number,
  today,
  list,
} from "../common/utils/format.js";
import Modal from "../common/components/Modal.vue";
const auth = useAuth(),
  ui = useUi(),
  router = useRouter(),
  items = ref([]),
  users = ref([]),
  q = ref(""),
  status = ref(""),
  show = ref(false),
  busy = ref(true),
  form = ref({});
const filtered = computed(() =>
  items.value.filter(
    (p) =>
      (!status.value || p.status === status.value) &&
      p.name.toLowerCase().includes(q.value.toLowerCase()),
  ),
);
const managers = computed(() =>
  users.value.filter(
    (u) => !u.is_blocked && ["admin", "manager"].includes(u.role),
  ),
);
onMounted(async () => {
  await ui.act(async () => {
    items.value = list(await api.get("/projects"));
    if (auth.admin) users.value = list(await api.get("/users")).sort((a, b) => a.full_name.localeCompare(b.full_name, "ru"));
  }, "");
  busy.value = false;
});
function create() {
  form.value = {
    name: "",
    description: "",
    manager_id: auth.user.user_id,
    start_date: today(),
    end_date: today(),
    planned_hours: 0,
    status: "active",
  };
  show.value = true;
}
async function save() {
  await ui.act(async () => {
    const p = await api.post("/projects", form.value);
    show.value = false;
    router.push("/projects/" + (p.project_id || p.project?.project_id));
  }, "Проект создан");
}
</script>
<template>
  <div class="page-head">
    <div>
      <h1>Проекты</h1>
      <p>Доступно {{ items.length }} проектов</p>
    </div>
    <button v-if="auth.manager" class="primary" @click="create">
      ＋ Новый проект
    </button>
  </div>
  <div class="filters">
    <input
      v-model="q"
      aria-label="Поиск проектов"
      placeholder="Найти проект"
    /><SearchSelect v-model="status" aria-label="Статус" :options="[{value:'',label:'Все статусы'}, ...Object.entries(projectStatuses).map(([value,label]) => ({value,label}))]" />
  </div>
  <p v-if="busy" class="loading">Загружаем проекты…</p>
  <div v-else class="table-wrap mobile-cards">
    <table>
      <thead>
        <tr>
          <th>Проект</th>
          <th>Статус</th>
          <th>Руководитель</th>
          <th>Начало</th>
          <th>Окончание</th>
          <th class="num">Плановый объём</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="p in filtered" :key="p.project_id">
          <td>
            <RouterLink :to="'/projects/' + p.project_id"
              ><strong>{{ p.name }}</strong></RouterLink
            ><span class="object-project">{{ p.description }}</span>
          </td>
          <td data-label="Статус">
            <span class="badge" :class="p.status">{{
              projectStatuses[p.status]
            }}</span>
          </td>
          <td data-label="Руководитель">
            {{
              p.manager_name ||
              users.find((u) => u.user_id === p.manager_id)?.full_name ||
              "Назначен"
            }}
          </td>
          <td data-label="Начало">{{ date(p.start_date) }}</td>
          <td data-label="Окончание">{{ date(p.end_date) }}</td>
          <td data-label="Плановый объём" class="num">
            {{ number(p.planned_hours) }} ч
          </td>
        </tr>
      </tbody>
    </table>
    <p v-if="!filtered.length" class="empty">Проекты не найдены</p>
  </div>
  <Modal v-if="show" title="Новый проект" @close="show = false"
    ><form @submit.prevent="save">
      <label
        >Название<input v-model="form.name" required maxlength="250" /></label
      ><label>Описание<textarea v-model="form.description" /></label>
      <div class="form-grid">
        <label
          >Начало<input v-model="form.start_date" type="date" required /></label
        ><label
          >Окончание<input
            v-model="form.end_date"
            type="date"
            :min="form.start_date"
            required /></label
        ><label
          >Плановый объём, ч<input
            v-model.number="form.planned_hours"
            type="number"
            step="0.01"
            min="0"
            required /></label
        ><label v-if="auth.admin"
          >Руководитель проекта<SearchSelect v-model="form.manager_id" :options="managers.map(u => ({value:u.user_id,label:u.full_name}))" placeholder="Выберите руководителя" required /></label
        ><label v-else
          >Руководитель проекта<input :value="auth.user.full_name" readonly
        /></label>
      </div>
      <button class="primary">Создать проект</button>
    </form></Modal
  >
</template>
