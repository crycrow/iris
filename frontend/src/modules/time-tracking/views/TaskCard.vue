<script setup>
import HistoryDetails from "../../../common/components/HistoryDetails.vue";
import { presentTaskEvent } from "../../../common/utils/history.js";
import { taskHierarchy, taskLabel } from "../taskFilters.js";
import SearchSelect from "../../../common/components/SearchSelect.vue";
import { ref, onMounted, computed } from "vue";
import { api } from "../../../common/api/client.js";
import { useUi } from "../../../common/stores/ui.js";
import { useAuth } from "../../../common/stores/auth.js";
import {
  taskStatuses,
  number,
} from "../../../common/utils/format.js";
import Modal from "../../../common/components/Modal.vue";
import RiskBadge from "../../../common/components/RiskBadge.vue";
const props = defineProps({
  task: Object,
  projectId: Number,
  tasks: Array,
  releases: Array,
  members: Array,
  risks: Array,
  editable: Boolean,
});
const emit = defineEmits(["close", "saved"]);
const ui = useUi(),
  auth = useAuth(),
  form = ref({ ...props.task }),
  activity = ref([]),
  comment = ref(""),
  assignment = ref({ user_id: props.members?.[0]?.user_id, planned_hours: 8 });
const sortedMembers = computed(() => [...(props.members || [])].sort((a, b) => a.full_name.localeCompare(b.full_name, "ru")));
const sortedAssignments = computed(() => [...(form.value.assignments || props.task.assignments || [])].sort((a, b) => a.full_name.localeCompare(b.full_name, "ru")));
const history = computed(() => activity.value.map((event) => ({
  ...event,
  ...presentTaskEvent(event, {
    users: props.members,
    tasks: props.tasks,
    releases: props.releases,
  }),
})));
const own = computed(() =>
  props.task.assignments?.some((a) => a.user_id === auth.user.user_id),
);
onMounted(() =>
  ui.act(async () => {
    const d = await api.get("/tasks/" + props.task.task_id);
    form.value = { ...(d.task || d) };
    activity.value = d.activity || [];
  }, ""),
);
async function save() {
  await ui.act(async () => {
    const body = props.editable
      ? {
          ...form.value,
          parent_task_id: form.value.parent_task_id || null,
          release_id: form.value.release_id || null,
        }
      : { status: form.value.status };
    await api.put("/tasks/" + props.task.task_id, body);
    emit("saved");
    emit("close");
  });
}
async function addComment() {
  await ui.act(async () => {
    await api.post("/tasks/" + props.task.task_id + "/comments", {
      text: comment.value,
    });
    comment.value = "";
    const d = await api.get("/tasks/" + props.task.task_id);
    activity.value = d.activity || [];
  }, "Комментарий добавлен");
}
async function removeAssignment(a) {
  if (!window.confirm("Снять назначение сотрудника?")) return;
  await ui.act(async () => {
    await api.del("/task-assignments/" + a.assignment_id);
    const d = await api.get("/tasks/" + props.task.task_id);
    form.value = d.task || d;
    emit("saved");
  }, "Назначение снято");
}
async function deleteTask() {
  if (!window.confirm("Удалить задачу?")) return;
  await ui.act(async () => {
    await api.del("/tasks/" + props.task.task_id);
    emit("saved");
    emit("close");
  }, "Задача удалена");
}
async function assign() {
  await ui.act(async () => {
    await api.post(`/projects/${props.projectId}/resources/assign`, {
      user_id: assignment.value.user_id,
      items: [
        {
          task_id: props.task.task_id,
          planned_hours: assignment.value.planned_hours,
        },
      ],
    });
    emit("saved");
    const d = await api.get("/tasks/" + props.task.task_id);
    form.value = d.task || d;
  }, "Исполнитель назначен");
}
</script>
<template>
  <Modal :title="'Задача № ' + task.task_id" @close="emit('close')"
    ><RiskBadge :risks="risks || []" />
    <form @submit.prevent="save">
      <label
        >Название<input
          v-model="form.name"
          :disabled="!editable"
          required /></label
      ><label
        >Описание<textarea v-model="form.description" :disabled="!editable" />
      </label>
      <div class="form-grid">
        <label
          >Статус<SearchSelect v-model="form.status" :disabled="!editable && !own" :options="Object.entries(taskStatuses).map(([value,label]) => ({value,label}))" /></label
        ><label
          >Прогресс, %<input
            type="number"
            min="0"
            max="100"
            v-model.number="form.progress_pct"
            :disabled="
              !editable || ['done', 'backlog', 'todo'].includes(form.status)
            " /></label
        ><label
          >Начало<input
            type="date"
            v-model="form.start_date"
            :disabled="!editable"
            required /></label
        ><label
          >Окончание<input
            type="date"
            v-model="form.due_date"
            :disabled="!editable"
            :min="form.start_date"
            required /></label
        ><label
          >Релиз<SearchSelect v-model="form.release_id" :disabled="!editable" :options="[{value:null,label:'Без релиза'}, ...releases.map(r => ({value:r.release_id,label:r.name}))]" /></label
        ><label
          >Родительская задача<SearchSelect v-model="form.parent_task_id" :disabled="!editable" :options="[{value:null,label:'Верхний уровень'}, ...taskHierarchy(tasks).filter(t => t.task_id !== task.task_id &amp;&amp; !t.is_milestone).map(t => ({value:t.task_id,label:taskLabel(t,tasks)}))]" /></label
        >
      </div>
      <button v-if="editable || own" class="primary">Сохранить задачу</button>
    </form>
    <h3 style="margin-top: 1.5rem">Исполнители и плановые часы</h3>
    <p v-for="a in sortedAssignments" :key="a.assignment_id">
      {{ a.full_name }} · {{ number(a.planned_hours) }} ч
      <button v-if="editable" class="small danger" @click="removeAssignment(a)">
        Снять назначение
      </button>
    </p>
    <form
      v-if="
        editable &&
        !task.is_milestone &&
        !tasks.some((t) => t.parent_task_id === task.task_id)
      "
      @submit.prevent="assign"
      class="form-grid"
    >
      <label
        >Сотрудник<SearchSelect v-model="assignment.user_id" :options="sortedMembers.map(u => ({value:u.user_id,label:u.full_name}))" placeholder="Выберите сотрудника" required /></label
      ><label
        >Плановые часы<input
          v-model.number="assignment.planned_hours"
          min="0"
          type="number"
          step=".5" /></label
      ><button>Назначить или изменить часы</button>
    </form>
    <h3 style="margin-top: 1.5rem">История задачи</h3>
    <div class="timeline">
      <article v-for="a in history" :key="a.activity_id">
        <small>Дата события {{ a.at }} · {{ a.user_name || members?.find((member) => member.user_id === a.user_id)?.full_name || "Автор не указан" }}</small>
        <p><strong>{{ a.title }}</strong></p>
        <HistoryDetails :details="a.details" />
      </article>
    </div>
    <form @submit.prevent="addComment">
      <label>Комментарий<textarea v-model="comment" required /></label
      ><button>Добавить комментарий</button>
    </form>
    <button
      v-if="editable"
      class="danger"
      style="margin-top: 1.5rem"
      @click="deleteTask"
    >
      Удалить задачу
    </button></Modal
  >
</template>
