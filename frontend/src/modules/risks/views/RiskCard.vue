<script setup>
import HistoryDetails from "../../../common/components/HistoryDetails.vue";
import { presentRiskEvent } from "../../../common/utils/history.js";
import SearchSelect from "../../../common/components/SearchSelect.vue";
import { ref, onMounted, computed } from "vue";
import { useRoute } from "vue-router";
import { useAuth } from "../../../common/stores/auth.js";
import {
  riskObjectLocation,
  safeReturn,
} from "../../../common/utils/riskNavigation.js";
import { api } from "../../../common/api/client.js";
import { useUi } from "../../../common/stores/ui.js";
import {
  date,
  number,
  list,
  riskStatuses,
  severities,
  actionStates,
} from "../../../common/utils/format.js";
const auth = useAuth();
const route = useRoute(),
  ui = useUi(),
  id = Number(route.params.id),
  data = ref(null),
  users = ref([]),
  responsible = ref(null),
  comment = ref(""),
  action = ref({ description: "", due_date: null }),
  busy = ref(false);
const returnTo = computed(() => safeReturn(route.query.returnTo));
const originProject = computed(
  () => Number(returnTo.value?.match(/^\/projects\/(\d+)/)?.[1]) || null,
);
const objectLocation = computed(() =>
  data.value
    ? riskObjectLocation(
        data.value.risk,
        data.value.can_manage,
        originProject.value,
      )
    : null,
);
async function load() {
  data.value = await api.get("/risks/" + id);
  responsible.value = data.value.risk.responsible_id;
}
onMounted(() =>
  ui.act(async () => {
    await load();
    if (data.value.can_manage) {
      users.value = list(await api.get("/users/options")).sort((a, b) => a.full_name.localeCompare(b.full_name, "ru"));
      if (!data.value.risk.is_viewed) {
        await api.post(`/risks/${id}/view`);
        await load();
      }
    }
  }, ""),
);
async function change(path, body) {
  busy.value = true;
  await ui.act(async () => {
    await api.post(`/risks/${id}/` + path, body);
    await load();
  });
  busy.value = false;
}
async function addAction() {
  await change("actions", action.value);
  action.value = { description: "", due_date: null };
}
async function addComment() {
  await change("comments", { text: comment.value });
  comment.value = "";
}
async function updateAction(a) {
  await ui.act(async () => {
    await api.put("/risk-actions/" + a.action_id, {
      execution_state: a.execution_state === "planned" ? "in_progress" : "done",
    });
    await load();
  });
}
const history = computed(() => {
  const risk = data.value?.risk;
  const people = [...users.value];
  if (risk?.responsible_id && !people.some((person) => person.user_id === risk.responsible_id))
    people.push({ user_id: risk.responsible_id, full_name: risk.responsible_name });
  return (data.value?.events || []).map((event) => ({
    ...event,
    ...presentRiskEvent(event, { users: people, actions: data.value?.actions }),
  }));
});
</script>
<template>
  <div v-if="data">
    <div class="page-head">
      <div>
        <RouterLink :to="returnTo || '/risks'">{{
          returnTo?.startsWith("/projects/")
            ? "← Вернуться в проект"
            : returnTo
              ? "← Назад"
              : "← Реестр рисков"
        }}</RouterLink>
        <h1>{{ data.risk.type_name }}</h1>
        <p>Выявлен {{ date(data.risk.detected_at) }}</p>
      </div>
      <div class="toolbar">
        <span class="badge" :class="data.risk.severity">{{
          severities[data.risk.severity]
        }}</span
        ><span class="badge" :class="data.risk.status">{{
          riskStatuses[data.risk.status]
        }}</span>
      </div>
    </div>
    <div v-if="data.risk.is_cause_resolved" class="alert">
      Основание риска устранено. Решение о закрытии принимает ответственный.
    </div>
    <div class="grid">
      <section class="card">
        <h2>Основание риска</h2>
        <p>{{ data.risk.description }}</p>
        <dl class="definition">
          <dt>Проект</dt>
          <dd>
            <RouterLink
              v-if="data.risk.project_id"
              :to="'/projects/' + data.risk.project_id"
              >{{ data.risk.project_name }}</RouterLink
            ><span v-else>Загрузка сотрудника</span>
          </dd>
          <dt>Задача</dt>
          <dd>
            <RouterLink
              v-if="data.risk.task_id && objectLocation"
              :to="objectLocation"
              >{{ data.risk.task_name }}</RouterLink
            ><span v-else>{{ data.risk.task_name || "Не указана" }}</span>
          </dd>
          <dt>Сотрудник</dt>
          <dd>
            <RouterLink
              v-if="data.risk.subject_user_id && objectLocation"
              :to="objectLocation"
              >{{ data.risk.subject_name }}</RouterLink
            ><span v-else>{{ data.risk.subject_name || "Не указан" }}</span>
          </dd>
          <dt>Показатель</dt>
          <dd>{{ number(data.risk.measured_value, 3) }}</dd>
          <dt>Ответственный</dt>
          <dd>{{ data.risk.responsible_name || "Не назначен" }}</dd>
        </dl>
        <p v-if="objectLocation">
          <RouterLink class="button" :to="objectLocation"
            >Перейти к объекту риска</RouterLink
          >
        </p>
        <p v-if="data.risk.recommendation">
          <strong>Рекомендация</strong><br />{{ data.risk.recommendation }}
        </p>
      </section>
      <section v-if="data.can_manage" class="card">
        <h2>Работа с риском</h2>
        <form
          @submit.prevent="change('assign', { responsible_id: responsible })"
        >
          <label
            >Ответственный<SearchSelect v-model="responsible" :options="users.map(u => ({value:u.user_id,label:u.full_name}))" placeholder="Выберите сотрудника" required /></label
          ><button
            :disabled="
              busy || ['closed', 'rejected'].includes(data.risk.status)
            "
          >
            Назначить
          </button>
        </form>
        <div class="toolbar" style="margin-top: 1rem">
          <button
            v-for="status in data.allowed_transitions || []"
            :key="status"
            :disabled="busy"
            @click="change('status', { status })"
          >
            {{ riskStatuses[status] }}
          </button>
        </div>
        <p
          v-if="['closed', 'rejected'].includes(data.risk.status)"
          class="muted"
        >
          Работа с риском завершена
        </p>
      </section>
    </div>
    <section class="card">
      <h2>Мероприятия по реагированию</h2>
      <div v-for="a in data.actions" :key="a.action_id" class="task-card">
        <div class="page-head">
          <div>
            <strong>{{ a.description }}</strong>
            <p>Срок {{ date(a.due_date) }}</p>
            <span class="badge" :class="a.execution_state">{{
              actionStates[a.execution_state]
            }}</span>
          </div>
          <button
            v-if="
              data.can_manage &&
              a.execution_state !== 'done' &&
              !['closed', 'rejected'].includes(data.risk.status)
            "
            @click="updateAction(a)"
          >
            {{
              a.execution_state === "planned"
                ? "Начать выполнение"
                : "Отметить выполненным"
            }}
          </button>
        </div>
      </div>
      <p v-if="!data.actions?.length" class="muted">
        Мероприятия пока не добавлены
      </p>
      <form
        v-if="
          data.can_manage && !['closed', 'rejected'].includes(data.risk.status)
        "
        @submit.prevent="addAction"
      >
        <div class="form-grid">
          <label
            >Новое мероприятие<input
              v-model="action.description"
              required /></label
          ><label
            >Срок<input v-model="action.due_date" type="date" required
          /></label>
        </div>
        <div><button :disabled="busy">Добавить мероприятие</button></div>
      </form>
    </section>
    <section class="card">
      <h2>История риска</h2>
      <div class="timeline">
        <article v-for="e in history" :key="e.event_id">
          <small>Дата события {{ e.at }} · {{ e.initiator_name || "Система" }}</small>
          <p><strong>{{ e.title }}</strong></p>
          <HistoryDetails :details="e.details" />
        </article>
      </div>
      <form v-if="data.can_manage" @submit.prevent="addComment">
        <label>Комментарий<textarea v-model="comment" required /></label>
        <div><button :disabled="busy">Добавить комментарий</button></div>
      </form>
    </section>
  </div>
  <p v-else class="loading">Загружаем карточку риска…</p>
</template>
