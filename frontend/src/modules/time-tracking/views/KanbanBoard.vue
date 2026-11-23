<script setup>
import { taskDepth } from "../taskFilters.js";
import { computed } from "vue";
import Draggable from "vuedraggable";
import {
  taskStatuses,
  taskProgress,
  date,
  today,
} from "../../../common/utils/format.js";
import RiskBadge from "../../../common/components/RiskBadge.vue";
import UiIcon from "../../../common/components/UiIcon.vue";
const props = defineProps({
  tasks: { type: Array, default: () => [] },
  indicators: { type: Object, default: () => ({}) },
  canEdit: { type: Function, default: () => false },
  canCreate: Boolean,
  visibleStatuses: { type: Array, default: () => [] },
});
const emit = defineEmits(["move", "open", "create"]);
const statuses = Object.keys(taskStatuses);
const columns = computed(() =>
  statuses
    .filter(
      (status) =>
        !props.visibleStatuses.length || props.visibleStatuses.includes(status),
    )
    .map((status) => ({
      status,
      tasks: props.tasks.filter((t) => t.status === status).map(t => ({ ...t, assignments: [...(t.assignments || [])].sort((a,b) => a.full_name.localeCompare(b.full_name, "ru")) })),
    })),
);
function changed(status, event) {
  if (event.added && props.canEdit(event.added.element))
    emit("move", event.added.element, status);
}
function move(t, n) {
  if (!props.canEdit(t)) return;
  const index = statuses.indexOf(t.status) + n;
  if (index >= 0 && index < statuses.length) emit("move", t, statuses[index]);
}
function initials(name) {
  return (
    String(name || "")
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((part) => part[0])
      .join("")
      .toUpperCase() || "?"
  );
}
function overdue(task) {
  return (
    task.due_date &&
    task.due_date < today() &&
    !["done", "cancelled"].includes(task.status)
  );
}
function shortDate(value) {
  if (!value) return "Без срока";
  return new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "short",
  }).format(new Date(String(value).slice(0, 10) + "T12:00:00"));
}
function openCard(task, event) {
  if (!event.target.closest("button, a, select")) emit("open", task);
}
</script>
<template>
  <div class="kanban-workspace">
    <div class="board" aria-label="Канбан-доска" tabindex="0">
      <section
        v-for="column in columns"
        :key="column.status"
        class="board-column"
        :class="`status-${column.status}`"
        :data-status="column.status"
      >
        <header class="column-heading">
          <h3>
            <i aria-hidden="true" />{{ taskStatuses[column.status] }}
            <span>{{ column.tasks.length }}</span>
          </h3>
          <button
            v-if="canCreate"
            type="button"
            class="column-add"
            :aria-label="`Добавить задачу в колонку «${taskStatuses[column.status]}»`"
            @click="emit('create', column.status)"
          >
            +
          </button>
        </header>
        <button
          v-if="canCreate"
          type="button"
          class="column-create"
          @click="emit('create', column.status)"
        >
          <span aria-hidden="true">+</span> Добавить задачу
        </button>
        <Draggable
          :model-value="column.tasks"
          item-key="task_id"
          group="tasks"
          class="board-list"
          :delay="150"
          :delay-on-touch-only="true"
          :touch-start-threshold="4"
          filter=".is-locked"
          :prevent-on-filter="false"
          ghost-class="task-ghost"
          chosen-class="task-chosen"
          :animation="180"
          :move="(e) => canEdit(e.draggedContext.element)"
          @change="changed(column.status, $event)"
          ><template #item="{ element: t }"
            ><article
              class="task-card"
              :style="{ marginLeft: `${Math.min(taskDepth(t, tasks), 4) * 16}px` }"
              :class="{
                'has-risk': indicators[t.task_id]?.length,
                'is-locked': !canEdit(t),
                'is-complete': t.status === 'done',
              }"
              @click="openCard(t, $event)"
            >
              <div class="task-eyebrow">
                <span class="task-reference">#{{ t.task_id }}</span
                ><span v-if="t.is_milestone" class="task-kind milestone-label">◆ Веха</span
                ><span v-else-if="t.parent_task_id" class="task-kind"
                  >Подзадача</span
                ><span
                  v-if="t.status === 'done'"
                  class="task-complete"
                  title="Задача завершена"
                  aria-label="Задача завершена"
                  ><UiIcon name="check" /></span
                ><span
                  v-else-if="indicators[t.task_id]?.length"
                  class="task-risk-marker"
                  :title="`Риски ${indicators[t.task_id].length}`"
                  aria-label="У задачи есть риски"
                  ><UiIcon name="risk" /></span
                >
              </div>
              <button class="task-name link" @click="emit('open', t)">
                <span v-if="t.is_milestone" class="milestone-label">◆ </span>{{ t.name }}
              </button>
              <div class="task-people">
                <div
                  class="avatar-stack"
                  :aria-label="
                    t.assignments?.map((a) => a.full_name).join(', ') ||
                    'Без исполнителя'
                  "
                >
                  <span
                    v-for="(person, index) in (t.assignments || []).slice(0, 3)"
                    :key="person.user_id"
                    class="task-avatar"
                    :class="`avatar-${index % 3}`"
                    :title="person.full_name"
                    >{{ initials(person.full_name) }}</span
                  ><span
                    v-if="(t.assignments?.length || 0) > 3"
                    class="task-avatar avatar-more"
                    >+{{ t.assignments.length - 3 }}</span
                  ><span
                    v-if="!t.assignments?.length"
                    class="task-avatar avatar-unassigned"
                    aria-hidden="true"
                    >○</span
                  >
                </div>
                <span class="task-assignee"
                  >{{
                    t.assignments?.length
                      ? t.assignments[0].full_name
                      : "Без исполнителя"
                  }}<template v-if="t.assignments?.length > 1">
                    и ещё {{ t.assignments.length - 1 }}</template
                  ></span
                >
              </div>
              <div class="task-meta">
                <span
                  class="task-due"
                  :class="{ overdue: overdue(t) }"
                  :title="`Срок ${date(t.due_date)}`"
                  ><svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
                    <rect x="3" y="4.5" width="14" height="12.5" rx="2" />
                    <path d="M6.5 2.5v4m7-4v4M3 8.5h14" /></svg
                  >{{ shortDate(t.due_date)
                  }}<span
                    v-if="overdue(t)"
                    class="overdue-dot"
                    aria-label="Срок истёк" /></span
                ><span class="task-percent"
                  >{{ taskProgress(t) }}<small>%</small></span
                >
              </div>
              <div
                class="task-progress"
                role="progressbar"
                :aria-valuenow="taskProgress(t)"
                aria-valuemin="0"
                aria-valuemax="100"
                :aria-label="`Готовность задачи ${t.name}`"
              >
                <span :style="{ width: taskProgress(t) + '%' }" />
              </div>
              <RiskBadge
                v-if="indicators[t.task_id]?.length"
                class="task-risks"
                :risks="indicators[t.task_id] || []"
              />
              <div v-if="canEdit(t)" class="actions task-move-actions">
                <button
                  class="small"
                  type="button"
                  :aria-label="`Перевести задачу «${t.name}» в предыдущий статус`"
                  :disabled="t.status === 'backlog'"
                  @click="move(t, -1)"
                >
                  ← Назад</button
                ><button
                  class="small"
                  type="button"
                  :aria-label="`Перевести задачу «${t.name}» в следующий статус`"
                  :disabled="t.status === 'cancelled'"
                  @click="move(t, 1)"
                >
                  Далее →
                </button>
              </div>
            </article></template
          ></Draggable
        >
        <p v-if="!column.tasks.length" class="column-empty">Задач пока нет</p>
      </section>
    </div>
  </div>
</template>

<style scoped>
.kanban-workspace {
  min-width: 0;
}
.column-heading h3 > i {
  display: block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--column-accent);
  flex-shrink: 0;
}
.board {
  display: grid;
  position: relative;
  grid-template-columns: repeat(auto-fit, minmax(min(245px, 100%), 1fr));
  grid-auto-flow: row;
  align-items: stretch;
  gap: 16px;
  min-width: 0;
  max-width: 100%;
  overflow: visible;
  padding: 0 0 16px;
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
  scroll-snap-type: x proximity;
}
.board-column {
  width: auto;
  display: flex;
  flex-direction: column;
  min-width: 0;
  padding: 12px;
  background: var(--inset);
  border: 1px solid var(--border);
  border-radius: 12px;
  scroll-snap-align: start;
}
.status-backlog {
  --column-accent: var(--muted);
}
.status-todo {
  --column-accent: var(--muted);
}
.status-dev {
  --column-accent: var(--accent);
}
.status-review {
  --column-accent: var(--secondary);
}
.status-testing {
  --column-accent: var(--secondary);
}
.status-release_wait {
  --column-accent: var(--warning);
}
.status-done {
  --column-accent: var(--success);
}
.status-cancelled {
  --column-accent: var(--muted);
}
.column-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 36px;
  gap: 8px;
  margin-bottom: 12px;
}
.column-heading h3 {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 14px;
  font-weight: 500;
  color: var(--text);
}
.column-heading h3 > span {
  padding: 0;
  border-radius: 5px;
  background: transparent;
  color: var(--muted);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
.column-add {
  flex-shrink: 0;
  min-height: 32px;
  width: 32px;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--muted);
  font-size: 19px;
  font-weight: 400;
  border-radius: 8px;
}
.column-add:hover {
  color: var(--column-accent);
  background: var(--card);
}
.board-list {
  min-height: 140px;
  max-height: min(480px, 55vh);
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-width: thin;
  padding-right: 4px;
  flex: 1;
}
.task-card {
  padding: 16px;
  margin: 0 0 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--card);
  box-shadow: none;
  cursor: grab;
  transition: background-color 160ms cubic-bezier(0.22, 1, 0.36, 1), border-color 160ms cubic-bezier(0.22, 1, 0.36, 1);
}
.task-card:hover {
  border-color: var(--muted);
  box-shadow: none;
  background: var(--card);
}
.task-card.is-locked {
  cursor: default;
}
.task-eyebrow {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 1.1rem;
  margin-bottom: 8px;
}
.task-reference {
  color: var(--muted);
  font-size: 12px;
  letter-spacing: 0;
}
.task-kind {
  color: var(--secondary);
  background: var(--inset);
  border-radius: 4px;
  padding: 2px 4px;
  font-size: 12px;
}
.task-kind.milestone-label { color: var(--milestone); background: color-mix(in srgb, var(--milestone) 10%, var(--card)); }
.task-risk-marker,
.task-complete {
  display: grid;
  place-items: center;
  margin-left: auto;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  font-size: 12px;
  font-weight: 600;
}
.task-risk-marker > svg,
.task-complete > svg {
  width: 18px;
  height: 18px;
}
.task-risk-marker {
  color: var(--warning);
  background: color-mix(in srgb, var(--warning) 8%, var(--card));
}
.task-complete {
  color: var(--success);
  background: color-mix(in srgb, var(--success) 8%, var(--card));
}
.task-card .task-name {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  width: 100%;
  min-height: 0;
  color: var(--text);
  font-size: 14px;
  font-weight: 500;
  line-height: 1.5;
  text-align: left;
  padding: 0;
}
.task-name:hover {
  color: var(--accent);
}
.task-people {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 16px 0 12px;
  min-width: 0;
}
.avatar-stack {
  display: flex;
  flex-shrink: 0;
  padding-right: 4px;
}
.task-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  margin-right: -4px;
  border: 2px solid var(--card);
  border-radius: 50%;
  background: var(--inset);
  color: var(--secondary);
  font-size: 12px;
  font-weight: 500;
}
.task-avatar.avatar-more,
.task-avatar.avatar-unassigned {
  background: var(--inset);
  color: var(--muted);
}
.task-assignee {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--muted);
  font-size: 12px;
}
.task-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.task-due {
  display: flex;
  align-items: center;
  gap: 4px;
  color: var(--muted);
  font-size: 12px;
}
.task-due svg {
  width: 18px;
  height: 18px;
  stroke: currentColor;
  stroke-width: 1.5;
}
.task-due.overdue {
  color: var(--danger);
}
.overdue-dot {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: currentColor;
}
.task-percent {
  color: var(--text);
  font-size: 12px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.task-percent small {
  font-size: 12px;
  color: var(--muted);
  margin-left: 1px;
}
.task-progress {
  height: 4px;
  overflow: hidden;
  margin-top: 8px;
  background: var(--inset);
  border-radius: 8px;
}
.task-progress > span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--accent);
}
.task-risks {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 12px;
}
.task-risks :deep(.badge) {
  margin: 0;
  font-size: 12px;
  padding: 2px 6px;
  border-radius: 4px;
}
.task-card .task-move-actions {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin: 12px 0 0;
  padding-top: 8px;
  border-top: 1px solid var(--border);
}
.task-move-actions button {
  min-height: 32px;
  padding: 4px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--muted);
  font-size: 12px;
}
.task-move-actions button:hover:not(:disabled) {
  color: var(--accent);
  background: var(--inset);
}
.column-create {
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-height: 36px;
  padding: 8px 12px;
  background: transparent;
  border: 1px dashed color-mix(in srgb, var(--column-accent) 25%, var(--border));
  border-radius: 8px;
  color: var(--muted);
  font-size: 12px;
  text-align: left;
}
.column-create > span {
  font-size: 17px;
  line-height: 1;
}
.column-create:hover {
  color: var(--column-accent);
  background: var(--card);
}
.column-empty {
  margin: -4px 0 16px;
  color: var(--muted);
  text-align: center;
  font-size: 12px;
}
.task-ghost {
  opacity: 0.3;
  background: var(--inset);
  border-style: dashed;
}
.task-chosen {
  box-shadow: 0 8px 24px rgb(0 0 0 / 8%);
  border-color: var(--accent);
}
@media (max-width: 600px) {
  .board {
    grid-template-columns: 1fr;
    gap: 12px;
  }
  .board-column {
  padding: 12px;
    background: var(--inset);
  border: 1px solid var(--border);
}
}
</style>
