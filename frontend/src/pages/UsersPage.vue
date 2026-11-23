<script setup>
import SearchSelect from "../common/components/SearchSelect.vue";
import { ref, computed, onMounted } from "vue";
import { api } from "../common/api/client.js";
import { useUi } from "../common/stores/ui.js";
import { roles, list } from "../common/utils/format.js";
import Modal from "../common/components/Modal.vue";
const ui = useUi(),
  users = ref([]),
  q = ref(""),
  show = ref(false),
  form = ref({});
async function load() {
  users.value = list(await api.get("/users")).sort((a, b) => a.full_name.localeCompare(b.full_name, "ru"));
}
onMounted(() => ui.act(load, ""));
const filtered = computed(() =>
  users.value.filter((u) =>
    `${u.full_name} ${u.login}`.toLowerCase().includes(q.value.toLowerCase()),
  ),
);
function edit(u) {
  form.value = u
    ? { ...u, password: "" }
    : {
        full_name: "",
        job_title: "",
        email: "",
        login: "",
        password: "",
        role: "employee",
        is_blocked: false,
      };
  show.value = true;
}
async function save() {
  await ui.act(async () => {
    const body = { ...form.value };
    if (!body.password) delete body.password;
    if (body.user_id) await api.put("/users/" + body.user_id, body);
    else await api.post("/users", body);
    show.value = false;
    await load();
  });
}
</script>
<template>
  <div class="page-head">
    <div>
      <h1>Пользователи</h1>
      <p>Учётные записи и права доступа</p>
    </div>
    <button class="primary" @click="edit()">＋ Новый пользователь</button>
  </div>
  <div class="filters">
    <input
      v-model="q"
      placeholder="Поиск по ФИО или логину"
      aria-label="Поиск пользователей"
    />
  </div>
  <div class="table-wrap mobile-cards">
    <table>
      <thead>
        <tr>
          <th>Сотрудник</th>
          <th>Логин</th>
          <th>Роль</th>
          <th>Состояние</th>
          <th />
        </tr>
      </thead>
      <tbody>
        <tr v-for="u in filtered" :key="u.user_id">
          <td>
            <strong>{{ u.full_name }}</strong
            ><small style="display: block"
              >{{ u.job_title }} · {{ u.email }}</small
            >
          </td>
          <td data-label="Логин">{{ u.login }}</td>
          <td data-label="Роль">{{ roles[u.role] }}</td>
          <td>{{ u.is_blocked ? "Заблокирован" : "Активен" }}</td>
          <td><button @click="edit(u)">Изменить</button></td>
        </tr>
      </tbody>
    </table>
  </div>
  <Modal
    v-if="show"
    :title="form.user_id ? 'Учётная запись' : 'Новый пользователь'"
    @close="show = false"
    ><form @submit.prevent="save">
      <div class="form-grid">
        <label>ФИО<input v-model="form.full_name" required /></label
        ><label>Должность<input v-model="form.job_title" /></label
        ><label>Рабочий email<input v-model="form.email" type="email" /></label
        ><label
          >Логин<input
            v-model="form.login"
            required
            autocomplete="off" /></label
        ><label
          >Роль<SearchSelect v-model="form.role" :options="Object.entries(roles).map(([value,label]) => ({value,label}))" /></label
        ><label
          >{{ form.user_id ? "Новый пароль, если требуется" : "Пароль"
          }}<input
            v-model="form.password"
            :required="!form.user_id"
            type="password"
            minlength="8"
            autocomplete="new-password"
        /></label>
      </div>
      <label class="check"
        ><input type="checkbox" v-model="form.is_blocked" />Заблокировать
        вход</label
      ><button class="primary">Сохранить</button>
    </form></Modal
  >
</template>
